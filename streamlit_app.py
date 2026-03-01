# -*- coding: utf-8 -*-
# ==============================================
#  Auditoría Forense - Visor Pericial Integrado
#  Archivo: streamlit_app.py
#  Versión: 1.0 estable (bloque completo)
# ==============================================

import base64
import re
import time
import unicodedata

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


# -------------------------
# CONFIGURACIÓN BÁSICA UI
# -------------------------
st.set_page_config(
    page_title="SISTEMA PERICIAL - VISOR INTEGRADO",
    layout="wide"
)

# -------------------------
# ESTADO INICIAL
# -------------------------
if "db_pericial" not in st.session_state:
    st.session_state.db_pericial = {}
if "auth" not in st.session_state:
    st.session_state.auth = False

# -------------------------
# SEGURIDAD SIMPLE
# -------------------------
def check_auth():
    st.title("🔐 Terminal Forense")
    master_from_secrets = st.secrets.get("MASTER_PASSWORD", None)  # opcional
    st.caption("Si estás probando y no tienes secrets, usa 1234")

    pw = st.text_input("Acceso Maestra:", type="password")
    if st.button("DESBLOQUEAR"):
        if (master_from_secrets and pw == master_from_secrets) or (not master_from_secrets and pw == "1234"):
            st.session_state.auth = True
            st.experimental_rerun()
        else:
            st.error("Clave incorrecta.")
            st.stop()

if not st.session_state.auth:
    check_auth()
    st.stop()

# -------------------------
# UTILIDADES
# -------------------------
def get_clean_id(texto) -> str:
    """Solo dígitos, sin ceros a la izquierda (para empatar CP)."""
    s = re.sub(r"\D", "", str(texto))
    return s.lstrip("0") or s

def _norm(s: str) -> str:
    s = str(s).strip().upper()
    s = unicodedata.normalize("NFKD", s)
    s = re.sub(r"[\W_]+", "", s)
    return s

def find_col(df: pd.DataFrame, candidates: list[str], required: bool = True):
    """Busca columna por nombres aproximados."""
    norm_map = {_norm(c): c for c in df.columns}
    for cand in candidates:
        if cand in norm_map:
            return norm_map[cand]
    for k, v in norm_map.items():
        if any(c in k for c in candidates):
            return v
    if required:
        raise KeyError(f"No se encontró ninguna de las columnas: {candidates}")
    return None

@st.cache_data(show_spinner=False)
def to_base64_pdf(file_bytes: bytes) -> str:
    return base64.b64encode(file_bytes).decode("utf-8")

def display_pdf(uploaded_file):
    """Muestra el PDF dentro de la app mediante iframe."""
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    file_bytes = uploaded_file.read()
    if not file_bytes:
        st.error("No se pudo leer el PDF (buffer vacío). Vuelva a cargar el archivo.")
        return
    base64_pdf = to_base64_pdf(file_bytes)
    iframe_html = f"""
        <iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="820" type="application/pdf"></iframe>
    """
    components.html(iframe_html, height=840, scrolling=True)

# Inicialización segura por si el form no se renderiza aún
submit = False

# -------------------------
# INTERFAZ PRINCIPAL
# -------------------------
st.title("🛡️ Auditoría Forense: Confrontación en Pantalla")

with st.sidebar:
    st.header("⚙️ Panel de Control")
    m_index = st.empty()
    m_map = st.empty()

    st.divider()
    ex_file = st.file_uploader("1. Matriz Excel", type=["xlsx"])
    pdf_files = st.file_uploader("2. Soportes PDFs", type=["pdf"], accept_multiple_files=True)

    if st.button("🗑️ REINICIO TOTAL"):
        st.session_state.clear()
        st.experimental_rerun()

# Solo procedemos cuando hay Excel y PDFs cargados
if ex_file and pdf_files:
    t_start = time.time()

    # Indexación de PDFs: mapeo por CP limpio → lista de archivos candidatos
    CP_PAT = re.compile(r"CP[_\-\s]?(\d+)", re.IGNORECASE)
    def extract_cp_from_name(name: str):
        m = CP_PAT.search(name)
        if m:
            return m.group(1).lstrip("0") or "0"
        digits = re.sub(r"\D", "", name)
        return digits.lstrip("0") or None

    pdf_index = {}
    for f in pdf_files:
        cp_id = extract_cp_from_name(f.name)
        if not cp_id:
            continue
        pdf_index.setdefault(cp_id, []).append(f)

    m_index.success(f"⚡ Indexación PDFs lista ({len(pdf_files)} archivos).")

    # Lectura de Excel
    try:
        df = pd.read_excel(ex_file)
    except Exception as e:
        st.error(f"No se pudo leer el Excel: {e}")
        st.stop()

    # Mapeo de columnas
    try:
        c_cp = find_col(df, ["CP", "CPAGO", "COMPAGO", "COMPROBANTE"])
    except KeyError:
        # fallback muy simple: primera columna
        c_cp = df.columns[0]
    try:
        c_fec = find_col(df, ["FECHA", "EMISION", "FECEMISION", "FECDOC"], required=False)
    except KeyError:
        c_fec = None

    m_map.success("🔍 Matriz lista.")

    # Tablero rápido
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Líneas Matriz", len(df))
    c2.metric("PDFs en Búfer", len(pdf_files))
    c3.metric(
        "Revisados OK",
        sum(1 for v in st.session_state.db_pericial.values() if v.get("Resultado_Final") == "OK"),
    )

    if c_fec:
        fec = pd.to_datetime(df[c_fec], errors="coerce")
        df["_ANIO"] = fec.dt.year
        df["_TRIM"] = fec.dt.quarter
        # ALERTA ejemplo: 2024 o trimestres 1-2 (ajusta a tu periodo real)
        traslape = df[(df["_ANIO"] == 2024) | (df["_TRIM"].isin([1, 2]))]
        c4.metric("Alertas Periodo", len(traslape), delta_color="inverse")
    else:
        traslape = pd.DataFrame()
        c4.metric("Alertas Periodo", 0)

    st.divider()

    # Selector de fila
    idx = st.selectbox(
        "🎯 Registro a Auditar:",
        range(len(df)),
        format_func=lambda x: f"Fila {x+1} | CP: {df.iloc[x][c_cp]}",
    )
    fila = df.iloc[idx]
    id_actual = get_clean_id(fila[c_cp])

    # Columnas de trabajo
    col_pdf, col_form = st.columns([1.5, 1])

    # ----- Columna PDF -----
    with col_pdf:
        st.subheader("🖼️ Visor de Evidencia")
        candidatos = pdf_index.get(id_actual, [])
        if len(candidatos) == 0:
            st.error(f"❌ DOCUMENTO NO ENCONTRADO PARA ID (CP): {fila[c_cp]}")
            st.info("Verifique que el nombre del PDF contenga el número de CP.")
        elif len(candidatos) == 1:
            display_pdf(candidatos[0])
        else:
            nombre = st.selectbox(
                "Se encontraron múltiples PDFs para este CP. Selecciona uno:",
                [f.name for f in candidatos],
            )
            sel = next(x for x in candidatos if x.name == nombre)
            display_pdf(sel)

    # ----- Columna Formulario -----
    with col_form:
        st.subheader("🖋️ Veredicto y Datos")
        # Muestra rápida de la fila (hasta 10 campos, ajusta si deseas)
        st.dataframe(fila.to_frame("Valor").head(10), use_container_width=True)

        # Aviso de posible traslape de periodo
        if not traslape.empty:
            try:
                en_traslape = any(
                    get_clean_id(x) == id_actual for x in traslape[c_cp].astype(str).tolist()
                )
                if en_traslape:
                    st.warning("🚨 REGISTRO DE PERIODO ANTERIOR")
            except Exception:
                pass

        # --- FORMULARIO DE VERIFICACIÓN (BLOQUE COMPLETO) ---
        with st.form(key="form_auditoria", clear_on_submit=False):
            st.markdown("### Validaciones por documento")

            # --- CP ---
            st.subheader("Comprobante de Pago (CP)")
            cp_num_pdf = st.text_input("Número de CP (PDF)", value="")
            cp_fecha_pdf = st.text_input("Fecha CP (PDF)", value="")  # o date_input si aplica
            cp_valor_pdf = st.number_input("Valor CP (PDF)", min_value=0.0, step=0.01, format="%.2f")
            cp_ok = st.selectbox("Validación CP (coincide con matriz)", ["OK", "MAL", "NO-LEÍBLE"], index=0)

            # --- CC ---
            st.subheader("Comprobante Contable (CC)")
            cc_num_pdf = st.text_input("Número de CC (PDF)", value="")
            cc_fecha_pdf = st.text_input("Fecha CC (PDF)", value="")
            cc_valor_debe = st.number_input("Valor en Debe (pago)", min_value=0.0, step=0.01, format="%.2f")
            cc_amort_anticipo = st.number_input("Amortización de anticipo (si aplica)", min_value=0.0, step=0.01, format="%.2f")
            cc_multas = st.number_input("Multas (si aplica)", min_value=0.0, step=0.01, format="%.2f")
            cc_ok = st.selectbox("Validación CC", ["OK", "MAL", "NO-LEÍBLE"], index=0)

            # --- Factura ---
            st.subheader("Factura")
            fac_ruc = st.text_input("RUC Proveedor (PDF/CP/CC)", value="")
            fac_num = st.text_input("Número de Factura (PDF)", value="")
            fac_fecha = st.text_input("Fecha de Factura (PDF)", value="")
            fac_subtotal = st.number_input("Subtotal (PDF)", min_value=0.0, step=0.01, format="%.2f")
            fac_iva_pct = st.number_input("IVA % (PDF)", min_value=0.0, step=0.01, format="%.2f")
            fac_iva_val = st.number_input("IVA Valor (PDF)", min_value=0.0, step=0.01, format="%.2f")
            fac_total = st.number_input("Total Factura (PDF)", min_value=0.0, step=0.01, format="%.2f")
            fac_ok = st.selectbox("Validación Cálculos Factura", ["OK", "MAL", "NO-LEÍBLE"], index=0)

            # --- Retención ---
            st.subheader("Comprobante de Retención")
            ret_num = st.text_input("Número Retención (PDF)", value="")
            ret_renta_pct = st.number_input("% Renta", min_value=0.0, step=0.01, format="%.2f")
            ret_renta_val = st.number_input("Valor Renta Retenida", min_value=0.0, step=0.01, format="%.2f")
            ret_iva_pct = st.number_input("% IVA Retenido", min_value=0.0, step=0.01, format="%.2f")
            ret_iva_val = st.number_input("Valor IVA Retenido", min_value=0.0, step=0.01, format="%.2f")
            ret_ok = st.selectbox("Validación Retención", ["OK", "MAL", "NO-LEÍBLE"], index=0)

            # --- SPI ---
            st.subheader("SPI (BCE)")
            spi_benef = st.text_input("Beneficiario (SPI)", value="")
            spi_valor = st.number_input("Valor Pagado (SPI)", min_value=0.0, step=0.01, format="%.2f")
            spi_ok = st.selectbox("Validación SPI (coincidencias de beneficiario/valor)", ["OK", "MAL", "NO-LEÍBLE"], index=0)

            # --- Coincidencias y alertas ---
            st.subheader("Cruces y Alertas")
            coincide_valores = st.selectbox("¿CP = CC = SPI (valor)?", ["Sí", "No", "No determinable"], index=0)
            fuera_anio = st.checkbox("Factura fuera del año en curso")
            fuera_trimestre = st.checkbox("Factura fuera del trimestre analizado")
            falta_pdf = st.checkbox("Falta PDF para esta línea")
            sobra_pdf = st.checkbox("Existe PDF sin línea asociada")

            # --- Resultado y hallazgos ---
            hallazgos = st.text_area("Hallazgos (detalle técnico)")
            claridad = st.slider("Claridad de lectura / evidencia (1= baja, 10= alta)", 1, 10, 7)
            resultado_final = st.selectbox("Resultado final", ["OK", "MAL", "NO-LEÍBLE", "INCOMPLETO"], index=0)

            # BOTÓN GUARDAR
            submit = st.form_submit_button("💾 GUARDAR RESULTADO")

            if submit:
                clave = f"{id_actual}::fila{idx+1}"
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
                    "Resultado_Final": resultado_final,
                    "PDFs_Vinculados": "; ".join([f.name for f in pdf_files if id_actual in f.name])
                }
                st.success("Guardado.")
                st.experimental_rerun()

    st.divider()
    # Reporte
    if st.button("📊 GENERAR REPORTE DE FIDELIDAD"):
        rep = pd.DataFrame.from_dict(st.session_state.db_pericial, orient="index")
        st.dataframe(rep, use_container_width=True)
        # descarga CSV
        if not rep.empty:
            csv = rep.to_csv(index=True).encode("utf-8")
            st.download_button(
                "⬇️ Descargar reporte (CSV)",
                data=csv,
                file_name="reporte_fidelidad.csv",
                mime="text/csv"
            )
        st.balloons()

else:
    st.info("👋 Xavier, cargue la Matriz y los PDFs para activar el Visor Pericial.")
