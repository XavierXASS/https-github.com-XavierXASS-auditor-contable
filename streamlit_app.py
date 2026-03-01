if ex_file and pdf_files:
    t_start = time.time()

    # ---------------------------------------------------
    # PANEL DE ESTADO EN VIVO: indexación y lectura
    # ---------------------------------------------------
    st.subheader("⏱️ Progreso de preparación")
    status = st.status("Preparando insumos…", expanded=True)
    progress = st.progress(0)
    log_area = st.empty()   # para mostrar última línea de log

    # Estructura de log de proceso por archivo
    if "carga_log" not in st.session_state:
        st.session_state.carga_log = []

    def log(msg: str, level: str = "info"):
        # Guarda en memoria y muestra la última línea
        st.session_state.carga_log.append({"ts": time.strftime("%H:%M:%S"), "level": level, "msg": msg})
        # Mostramos solo la última línea en vivo para no saturar la UI
        icon = {"info": "ℹ️", "ok": "✅", "warn": "⚠️", "err": "❌"}.get(level, "ℹ️")
        log_area.write(f"{icon} {msg}")

    # ---- FASE 1: INDEXACIÓN DE PDFs (por CP) ----
    CP_PAT = re.compile(r"CP[_\\-\\s]?(\\d+)", re.IGNORECASE)

    def extract_cp_from_name(name: str):
        m = CP_PAT.search(name)
        if m:
            return m.group(1).lstrip("0") or "0"
        digits = re.sub(r"\\D", "", name)
        return digits.lstrip("0") or None

    total_pdfs = len(pdf_files)
    pdf_index = {}
    resultados_index = []  # para informe: por cada PDF, CP extraído y estado

    status.update(label="Indexando PDFs…", state="running")
    for i, f in enumerate(pdf_files, start=1):
        try:
            cp_id = extract_cp_from_name(f.name)
            if not cp_id:
                resultados_index.append({"archivo": f.name, "cp_extraido": None, "estado": "SIN_CP_EN_NOMBRE"})
                log(f"Sin CP en nombre: {f.name}", "warn")
                continue
            pdf_index.setdefault(cp_id, []).append(f)
            resultados_index.append({"archivo": f.name, "cp_extraido": cp_id, "estado": "OK"})
            if i % 10 == 0 or i == total_pdfs:
                log(f"Indexados {i}/{total_pdfs} PDFs (CP actual: {cp_id})", "info")
        except Exception as e:
            resultados_index.append({"archivo": f.name, "cp_extraido": None, "estado": f"ERROR: {e}"})
            log(f"Error indexando {f.name}: {e}", "err")
        progress.progress(int(i * 100 / max(1, total_pdfs)))

    # ---- FASE 2: LECTURA DE MATRIZ ----
    status.update(label="Leyendo matriz Excel…", state="running")
    try:
        df = pd.read_excel(ex_file)
        log(f"Matriz cargada con {len(df)} filas.", "ok")
    except Exception as e:
        status.update(label=f"Error leyendo Excel: {e}", state="error")
        st.error(f"No se pudo leer el Excel: {e}")
        st.stop()

    # Detección de columnas CP y FECHA
    def _norm(s: str) -> str:
        s = str(s).strip().upper()
        s = unicodedata.normalize("NFKD", s)
        s = re.sub(r"[\\W_]+", "", s)
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
            raise KeyError(f"No se encontró ninguna de las columnas: {candidates}")
        return None

    try:
        c_cp = find_col(df, ["CP", "CPAGO", "COMPAGO", "COMPROBANTE"])
    except KeyError:
        c_cp = df.columns[0]  # fallback
        st.toast("Usando la primera columna como CP (no se halló 'CP').", icon="⚠️")

    try:
        c_fec = find_col(df, ["FECHA", "EMISION", "FECEMISION", "FECDOC"], required=False)
    except KeyError:
        c_fec = None

    # Métricas base
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Líneas Matriz", len(df))
    c2.metric("PDFs en Búfer", total_pdfs)
    c3.metric(
        "Revisados OK",
        sum(1 for v in st.session_state.db_pericial.values() if v.get("Resultado_Final") == "OK"),
    )

    if c_fec:
        fec = pd.to_datetime(df[c_fec], errors="coerce")
        df["_ANIO"] = fec.dt.year
        df["_TRIM"] = fec.dt.quarter
        # Parámetros en sidebar: anio_objetivo y trimestre_objetivo ya existen
        if trimestre_objetivo is None:
            traslape = df[df["_ANIO"] != anio_objetivo]
        else:
            traslape = df[(df["_ANIO"] != anio_objetivo) | (df["_TRIM"] != trimestre_objetivo)]
        c4.metric("Alertas de Periodo", len(traslape), delta_color="inverse")
    else:
        traslape = pd.DataFrame()
        c4.metric("Alertas de Periodo", 0)

    # ---- FASE 3: CRUCE MATRIZ vs PDFs (faltantes/sobrantes) con progreso ----
    status.update(label="Cruzando Matriz vs PDFs…", state="running")
    cruce_result = []  # para cada fila: CP, tiene_pdf, cuenta_candidatos
    faltantes = 0
    for i in range(len(df)):
        fila_cp = str(df.iloc[i][c_cp])
        id_cp = re.sub(r"\\D", "", fila_cp).lstrip("0") or re.sub(r"\\D", "", fila_cp)
        candidatos = pdf_index.get(id_cp, [])
        tiene = len(candidatos) > 0
        cruce_result.append({
            "fila": i + 1,
            "cp_matriz": fila_cp,
            "cp_id": id_cp,
            "pdfs_encontrados": len(candidatos),
            "estado": "OK" if tiene else "SIN_PDF"
        })
        if not tiene:
            faltantes += 1
        if (i + 1) % 20 == 0 or (i + 1) == len(df):
            log(f"Cruzando fila {i+1}/{len(df)} (CP {id_cp})", "info")
        progress.progress(int((i + 1) * 100 / max(1, len(df))))

    # PDFs sobrantes (con CP no presente en la matriz)
    set_matriz = { (re.sub(r"\\D", "", str(df.iloc[i][c_cp])).lstrip("0") or re.sub(r"\\D", "", str(df.iloc[i][c_cp]))) for i in range(len(df)) }
    sobrantes = []
    for cp_id, files in pdf_index.items():
        if cp_id not in set_matriz:
            for f in files:
                sobrantes.append({"archivo": f.name, "cp_id": cp_id, "estado": "PDF_SIN_FILA"})

    # Cierro panel de estado
    status.update(
        label=f"Preparación completa en {time.time()-t_start:.1f} s — Faltantes: {faltantes} | Sobrantes: {len(sobrantes)}",
        state="complete"
    )
    st.toast("Carga y cruce terminados.", icon="✅")

    # ---------------------------------------------------
    # RESÚMENES EN PANTALLA
    # ---------------------------------------------------
    st.divider()
    st.markdown("### 📋 Resumen de Indexación de PDFs")
    st.dataframe(pd.DataFrame(resultados_index), use_container_width=True, hide_index=True)

    st.markdown("### 🔎 Cruce Matriz ↔ PDFs (por fila)")
    st.dataframe(pd.DataFrame(cruce_result), use_container_width=True, hide_index=True)

    if sobrantes:
        st.markdown("### 🗂️ PDFs sin fila asociada (Sobrantes)")
        st.dataframe(pd.DataFrame(sobrantes), use_container_width=True, hide_index=True)

    # Botones de exportación
    colx, coly, colz = st.columns(3)
    with colx:
        if st.button("⬇️ Descargar log de carga (CSV)"):
            df_log = pd.DataFrame(st.session_state.carga_log)
            st.download_button(
                "Descargar ahora",
                data=df_log.to_csv(index=False).encode("utf-8"),
                file_name="log_carga.csv",
                mime="text/csv",
                use_container_width=True
            )
    with coly:
        st.download_button(
            "⬇️ Cruce Matriz ↔ PDFs (CSV)",
            data=pd.DataFrame(cruce_result).to_csv(index=False).encode("utf-8"),
            file_name="cruce_matriz_pdfs.csv",
            mime="text/csv",
            use_container_width=True
        )
    with colz:
        if sobrantes:
            st.download_button(
                "⬇️ PDFs Sobrantes (CSV)",
                data=pd.DataFrame(sobrantes).to_csv(index=False).encode("utf-8"),
                file_name="pdfs_sobrantes.csv",
                mime="text/csv",
                use_container_width=True
            )

    # ---------------------------------------------------
    # FLUJO NORMAL: Selección de registro + visor + formulario
    # ---------------------------------------------------
    st.divider()
    idx = st.selectbox(
        "🎯 Registro a Auditar:",
        range(len(df)),
        format_func=lambda x: f"Fila {x+1} | CP: {df.iloc[x][c_cp]}"
    )
    fila = df.iloc[idx]
    id_actual = re.sub(r"\\D", "", str(fila[c_cp])).lstrip("0") or re.sub(r"\\D", "", str(fila[c_cp]))

    col_pdf, col_form = st.columns([1.5, 1])

    with col_pdf:
        st.subheader("🖼️ Visor de Evidencia")
        candidatos = pdf_index.get(id_actual, [])
        if len(candidatos) == 0:
            st.error(f"❌ DOCUMENTO NO ENCONTRADO PARA CP: {fila[c_cp]}")
            st.info("Verifique que el nombre del PDF contenga el número de CP.")
        elif len(candidatos) == 1:
            display_pdf(candidatos[0])
        else:
            nombre = st.selectbox(
                "Se encontraron múltiples PDFs para este CP. Selecciona uno:",
                [f.name for f in candidatos]
            )
            sel = next(x for x in candidatos if x.name == nombre)
            display_pdf(sel)

    with col_form:
        st.subheader("🖋️ Veredicto y Datos")
        st.dataframe(fila.to_frame("Valor").head(10), use_container_width=True)

        if not traslape.empty:
            try:
                en_traslape = any(
                    (re.sub(r"\\D", "", str(x)).lstrip("0") or re.sub(r"\\D", "", str(x))) == id_actual
                    for x in traslape[c_cp].astype(str).tolist()
                )
                if en_traslape:
                    st.warning("🚨 REGISTRO FUERA DEL PERIODO OBJETIVO")
            except Exception:
                pass

        with st.form(key="form_auditoria", clear_on_submit=False):
            st.markdown("### Validaciones por documento")

            st.subheader("Comprobante de Pago (CP)")
            cp_num_pdf = st.text_input("Número de CP (PDF)", value="")
            cp_fecha_pdf = st.text_input("Fecha CP (PDF)", value="")
            cp_valor_pdf = st.number_input("Valor CP (PDF)", min_value=0.0, step=0.01, format="%.2f")
            cp_ok = st.selectbox("Validación CP (coincide con matriz)", ["OK", "MAL", "NO-LEÍBLE"], index=0)

            st.subheader("Comprobante Contable (CC)")
            cc_num_pdf = st.text_input("Número de CC (PDF)", value="")
            cc_fecha_pdf = st.text_input("Fecha CC (PDF)", value="")
            cc_valor_debe = st.number_input("Valor en Debe (pago)", min_value=0.0, step=0.01, format="%.2f")
            cc_amort_anticipo = st.number_input("Amortización de anticipo (si aplica)", min_value=0.0, step=0.01, format="%.2f")
            cc_multas = st.number_input("Multas (si aplica)", min_value=0.0, step=0.01, format="%.2f")
            cc_ok = st.selectbox("Validación CC", ["OK", "MAL", "NO-LEÍBLE"], index=0)

            st.subheader("Factura")
            fac_ruc = st.text_input("RUC Proveedor (PDF/CP/CC)", value="")
            fac_num = st.text_input("Número de Factura (PDF)", value="")
            fac_fecha = st.text_input("Fecha de Factura (PDF)", value="")
            fac_subtotal = st.number_input("Subtotal (PDF)", min_value=0.0, step=0.01, format="%.2f")
            fac_iva_pct = st.number_input("IVA % (PDF)", min_value=0.0, step=0.01, format="%.2f")
            fac_iva_val = st.number_input("IVA Valor (PDF)", min_value=0.0, step=0.01, format="%.2f")
            fac_total = st.number_input("Total Factura (PDF)", min_value=0.0, step=0.01, format="%.2f")
            fac_ok = st.selectbox("Validación Cálculos Factura", ["OK", "MAL", "NO-LEÍBLE"], index=0)

            st.subheader("Comprobante de Retención")
            ret_num = st.text_input("Número Retención (PDF)", value="")
            ret_renta_pct = st.number_input("% Renta", min_value=0.0, step=0.01, format="%.2f")
            ret_renta_val = st.number_input("Valor Renta Retenida", min_value=0.0, step=0.01, format="%.2f")
            ret_iva_pct = st.number_input("% IVA Retenido", min_value=0.0, step=0.01, format="%.2f")
            ret_iva_val = st.number_input("Valor IVA Retenido", min_value=0.0, step=0.01, format="%.2f")
            ret_ok = st.selectbox("Validación Retención", ["OK", "MAL", "NO-LEÍBLE"], index=0)

            st.subheader("SPI (BCE)")
            spi_benef = st.text_input("Beneficiario (SPI)", value="")
            spi_valor = st.number_input("Valor Pagado (SPI)", min_value=0.0, step=0.01, format="%.2f")
            spi_ok = st.selectbox("Validación SPI (coincidencias de beneficiario/valor)", ["OK", "MAL", "NO-LEÍBLE"], index=0)

            st.subheader("Cruces y Alertas")
            coincide_valores = st.selectbox("¿CP = CC = SPI (valor)?", ["Sí", "No", "No determinable"], index=0)
            fuera_anio = st.checkbox("Factura fuera del año en curso")
            fuera_trimestre = st.checkbox("Factura fuera del trimestre analizado")
            falta_pdf = st.checkbox("Falta PDF para esta línea")
            sobra_pdf = st.checkbox("Existe PDF sin línea asociada")

            hallazgos = st.text_area("Hallazgos (detalle técnico)")
            claridad = st.slider("Claridad de lectura / evidencia (1= baja, 10= alta)", 1, 10, 7)
            resultado_final = st.selectbox("Resultado final", ["OK", "MAL", "NO-LEÍBLE", "INCOMPLETO"], index=0)

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
                    "PDFs_Vinculados": "; ".join([f.name for f in pdf_files if (re.sub(r"\\D", "", f.name).lstrip("0") or re.sub(r"\\D", "", f.name)) == id_actual])
                }
                st.success("Guardado.")
                st.rerun()

    st.divider()
    # ---- REPORTE RESUMIDO (lo que ya tienes + exportables) ----
    if st.button("📊 GENERAR REPORTE DE FIDELIDAD"):
        rep = pd.DataFrame.from_dict(st.session_state.db_pericial, orient="index")
        st.dataframe(rep, use_container_width=True)
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
