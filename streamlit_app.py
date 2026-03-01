with st.form("form_auditoria", clear_on_submit=False):
    st.markdown("### Validaciones por documento")

    # --- CP ---
    st.subheader("Comprobante de Pago (CP)")
    cp_num_pdf = st.text_input("Número de CP (PDF)", value="")
    cp_fecha_pdf = st.text_input("Fecha CP (PDF)", value="")  # o date_input si aplica
    cp_valor_pdf = st.number_input("Valor CP (PDF)", min_value=0.0, step=0.01, format="%.2f")
    cp_ok = st.selectbox("Validación CP (coincide con matriz)", ["OK","MAL","NO-LEÍBLE"], index=0)

    # --- CC ---
    st.subheader("Comprobante Contable (CC)")
    cc_num_pdf = st.text_input("Número de CC (PDF)", value="")
    cc_fecha_pdf = st.text_input("Fecha CC (PDF)", value="")
    cc_valor_debe = st.number_input("Valor en Debe (pago)", min_value=0.0, step=0.01, format="%.2f")
    cc_amort_anticipo = st.number_input("Amortización de anticipo (si aplica)", min_value=0.0, step=0.01, format="%.2f")
    cc_multas = st.number_input("Multas (si aplica)", min_value=0.0, step=0.01, format="%.2f")
    cc_ok = st.selectbox("Validación CC", ["OK","MAL","NO-LEÍBLE"], index=0)

    # --- Factura ---
    st.subheader("Factura")
    fac_ruc = st.text_input("RUC Proveedor (PDF/CP/CC)", value="")
    fac_num = st.text_input("Número de Factura (PDF)", value="")
    fac_fecha = st.text_input("Fecha de Factura (PDF)", value="")
    fac_subtotal = st.number_input("Subtotal (PDF)", min_value=0.0, step=0.01, format="%.2f")
    fac_iva_pct = st.number_input("IVA % (PDF)", min_value=0.0, step=0.01, format="%.2f")
    fac_iva_val = st.number_input("IVA Valor (PDF)", min_value=0.0, step=0.01, format="%.2f")
    fac_total = st.number_input("Total Factura (PDF)", min_value=0.0, step=0.01, format="%.2f")
    fac_ok = st.selectbox("Validación Cálculos Factura", ["OK","MAL","NO-LEÍBLE"], index=0)

    # --- Retención ---
    st.subheader("Comprobante de Retención")
    ret_num = st.text_input("Número Retención (PDF)", value="")
    ret_renta_pct = st.number_input("% Renta", min_value=0.0, step=0.01, format="%.2f")
    ret_renta_val = st.number_input("Valor Renta Retenida", min_value=0.0, step=0.01, format="%.2f")
    ret_iva_pct = st.number_input("% IVA Retenido", min_value=0.0, step=0.01, format="%.2f")
    ret_iva_val = st.number_input("Valor IVA Retenido", min_value=0.0, step=0.01, format="%.2f")
    ret_ok = st.selectbox("Validación Retención", ["OK","MAL","NO-LEÍBLE"], index=0)

    # --- SPI ---
    st.subheader("SPI (BCE)")
    spi_benef = st.text_input("Beneficiario (SPI)", value="")
    spi_valor = st.number_input("Valor Pagado (SPI)", min_value=0.0, step=0.01, format="%.2f")
    spi_ok = st.selectbox("Validación SPI (coincidencias de beneficiario/valor)", ["OK","MAL","NO-LEÍBLE"], index=0)

    # --- Coincidencias y alertas ---
    st.subheader("Cruces y Alertas")
    coincide_valores = st.selectbox("¿CP = CC = SPI (valor)?", ["Sí","No","No determinable"], index=0)
    fuera_anio = st.checkbox("Factura fuera del año en curso")
    fuera_trimestre = st.checkbox("Factura fuera del trimestre analizado")
    falta_pdf = st.checkbox("Falta PDF para esta línea")
    sobra_pdf = st.checkbox("Existe PDF sin línea asociada")

    # --- Resultado y hallazgos ---
    hallazgos = st.text_area("Hallazgos (detalle técnico)")
    claridad = st.slider("Claridad de lectura / evidencia (1= baja, 10= alta)", 1, 10, 7)
    resultado_final = st.selectbox("Resultado final", ["OK", "MAL", "NO-LEÍBLE", "INCOMPLETO"], index=0)

    submit = st.form_submit_button("💾 GUARDAR RESULTADO")

if submit:
    # Aquí persistimos con la llave id_actual (tu CP limpio) más ID de fila para evitar colisiones
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
    st.rerun()
