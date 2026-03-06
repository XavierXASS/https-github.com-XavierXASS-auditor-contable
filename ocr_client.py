# -*- coding: utf-8 -*-
"""
ocr_client.py
Utilitarios para OCR online (OCR.Space) integrables en Streamlit sin instalaciones locales.
- Detecta capa de texto por página (si existe) para evitar OCR innecesario.
- Divide PDFs en segmentos (páginas) para respetar límites del proveedor.
- Unifica resultados en TXT y JSON.
- Descarga PDF buscable si el proveedor lo incluye (cuando se solicita).
"""

from __future__ import annotations
import io
import json
import base64
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any

import requests
from PyPDF2 import PdfReader, PdfWriter

# ---------------------------------------------------------------------
# Configuración por defecto (puedes sobreescribir desde Streamlit)
# ---------------------------------------------------------------------
DEFAULT_API_ENDPOINT = "https://api.ocr.space/parse/image"
DEFAULT_OCR_ENGINE = 2   # buen balance para números/símbolos
DEFAULT_LANG = "spa"     # idioma por defecto (puedes usar "spa,eng")
DEFAULT_TIMEOUT = 180    # segundos

# Límite recomendado para free: 3 páginas por llamada (puedes ajustar si usas PRO key)
DEFAULT_MAX_PAGES_PER_CALL = 3

@dataclass
class OcrChunkResult:
    """Resultado de un segmento OCR (un subconjunto de páginas)."""
    json_raw: Dict[str, Any]
    text_per_page: List[str]
    searchable_pdf_urls: List[str]  # URLs o base64, según lo devuelva el proveedor

@dataclass
class OcrFullResult:
    """Resultado consolidado de todo el documento."""
    pages: int
    text_per_page: List[str]
    merged_text: str
    json_pages: List[Dict[str, Any]]
    searchable_pdf_urls: List[str]  # si el proveedor retornó URLs por segmento

# ---------------------------------------------------------------------
# Detección de capa de texto (por página)
# ---------------------------------------------------------------------
def pdf_has_text_layer_per_page(pdf_bytes: bytes) -> List[bool]:
    flags = []
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            text = page.extract_text() or ""
            flags.append(bool(text.strip()))
        return flags
    except Exception:
        # Si no se puede leer, asumimos sin texto
        return []

def extract_text_from_pdf_textlayer(pdf_bytes: bytes) -> List[str]:
    texts = []
    reader = PdfReader(io.BytesIO(pdf_bytes))
    for page in reader.pages:
        texts.append((page.extract_text() or "").rstrip())
    return texts

# ---------------------------------------------------------------------
# Particionado de PDF por rangos de página
# ---------------------------------------------------------------------
def split_pdf_into_ranges(pdf_bytes: bytes, ranges: List[Tuple[int, int]]) -> List[bytes]:
    """
    ranges: lista de (start, end) 1-based inclusive.
    """
    out_list: List[bytes] = []
    reader = PdfReader(io.BytesIO(pdf_bytes))
    n = len(reader.pages)

    for (start, end) in ranges:
        start0, end0 = max(1, start) - 1, min(n, end) - 1
        writer = PdfWriter()
        for p in range(start0, end0 + 1):
            writer.add_page(reader.pages[p])
        buf = io.BytesIO()
        writer.write(buf)
        out_list.append(buf.getvalue())
    return out_list

def make_sequential_ranges(total_pages: int, chunk_size: int) -> List[Tuple[int, int]]:
    ranges = []
    p = 1
    while p <= total_pages:
        q = min(p + chunk_size - 1, total_pages)
        ranges.append((p, q))
        p = q + 1
    return ranges

# ---------------------------------------------------------------------
# Llamada a OCR.Space (una sola llamada por archivo/segmento)
# ---------------------------------------------------------------------
def call_ocr_space(
    file_bytes: bytes,
    filename: str,
    language: str = DEFAULT_LANG,
    api_key: Optional[str] = None,
    create_searchable_pdf: bool = False,
    endpoint: str = DEFAULT_API_ENDPOINT,
    ocr_engine: int = DEFAULT_OCR_ENGINE,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    files = {"file": (filename, file_bytes)}
    data = {
        "language": language,
        "isOverlayRequired": False,
        "OCREngine": ocr_engine,
    }
    if create_searchable_pdf:
        data["isCreateSearchablePdf"] = True
        # Si False: deja visible la capa de texto; si True: oculta capa de texto (solo seleccionable).
        data["isSearchablePdfHideTextLayer"] = False

    headers = {}
    if api_key:
        headers["apikey"] = api_key

    resp = requests.post(endpoint, files=files, data=data, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

# ---------------------------------------------------------------------
# Orquestación de OCR por PDF completo: detecta texto y trocea si hace falta
# ---------------------------------------------------------------------
def ocr_pdf_with_fallback(
    pdf_bytes: bytes,
    filename: str,
    language: str = DEFAULT_LANG,
    api_key: Optional[str] = None,
    create_searchable_pdf: bool = False,
    max_pages_per_call: int = DEFAULT_MAX_PAGES_PER_CALL,
) -> OcrFullResult:
    """
    Lógica:
    - Detecta por página si ya hay texto. Si lo hay, lo usa.
    - Para páginas sin texto, llama al API en segmentos de hasta max_pages_per_call.
    - Consolida el resultado.
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    total_pages = len(reader.pages)
    has_text_flags = pdf_has_text_layer_per_page(pdf_bytes)

    # 1) Extraer primero todo lo que tenga capa de texto
    text_from_layer = extract_text_from_pdf_textlayer(pdf_bytes) if any(has_text_flags) else [""] * total_pages

    # 2) Preparar rangos para OCR solo en páginas sin texto
    pages_to_ocr = [i + 1 for i, flag in enumerate(has_text_flags) if not flag] if has_text_flags else list(range(1, total_pages + 1))
    ranges = make_sequential_ranges(len(pages_to_ocr), max_pages_per_call) if pages_to_ocr else []

    # Reconvertir ranges (índices relativos) a (start,end) absolutos sobre el PDF
    abs_ranges: List[Tuple[int, int]] = []
    for rstart, rend in ranges:
        # rstart/rend son posiciones en pages_to_ocr (1-based)
        start_abs = pages_to_ocr[rstart - 1]
        end_abs = pages_to_ocr[rend - 1]
        abs_ranges.append((start_abs, end_abs))

    text_per_page = [""] * total_pages
    searchable_pdf_urls: List[str] = []
    json_pages: List[Dict[str, Any]] = []

    # Inicializa con el texto de capa (si lo hay)
    for i in range(total_pages):
        text_per_page[i] = text_from_layer[i] if i < len(text_from_layer) else ""

    # 3) Ejecutar OCR por segmentos (solo páginas que lo necesitan)
    for (start, end) in abs_ranges:
        segment_bytes = split_pdf_into_ranges(pdf_bytes, [(start, end)])[0]
        seg_name = f"{filename}_p{start}-{end}.pdf"
        result = call_ocr_space(
            file_bytes=segment_bytes,
            filename=seg_name,
            language=language,
            api_key=api_key,
            create_searchable_pdf=create_searchable_pdf,
        )
        # Parsear resultado
        parsed = result.get("ParsedResults") or []
        json_pages.append(result)

        # Asignar texto por página según el orden devuelto
        # OCR.Space devuelve texto concatenado por "ParsedResults" (usualmente 1 por input),
        # y en "TextOverlay/Lines" puede haber detalle. Aquí tomamos "ParsedText".
        if parsed:
            parsed_text = parsed[0].get("ParsedText", "") or ""
            # Heurística: si el segmento tiene N páginas, el proveedor no siempre separa por saltos claros.
            # Intento: si hay form feeds, split; si no, dejamos texto único.
            candidate_pages = parsed_text.split("\f")
            seg_pages_count = end - start + 1
            if len(candidate_pages) >= seg_pages_count:
                for idx in range(seg_pages_count):
                    text_per_page[start + idx - 1] = (text_per_page[start + idx - 1] + "\n" + candidate_pages[idx]).strip()
            else:
                # Texto único: lo asignamos concatenado a todas las páginas del rango
                for idx in range(seg_pages_count):
                    text_per_page[start + idx - 1] = (text_per_page[start + idx - 1] + "\n" + parsed_text).strip()

            # PDF buscable: URL o base64 (varía). Guardamos URLs si vienen.
            # Algunas respuestas traen 'SearchablePDFURL' por cada ParsedResult.
            for p in parsed:
                if p.get("SearchablePDFURL"):
                    searchable_pdf_urls.append(p["SearchablePDFURL"])

    merged_text = "\n\n".join([f"--- Página {i+1} ---\n{txt}".rstrip() for i, txt in enumerate(text_per_page)])
    return OcrFullResult(
        pages=total_pages,
        text_per_page=text_per_page,
        merged_text=merged_text,
        json_pages=json_pages,
        searchable_pdf_urls=searchable_pdf_urls,
    )

# ---------------------------------------------------------------------
# Procesar imágenes (JPG/PNG/TIFF/WEBP)
# ---------------------------------------------------------------------
def ocr_image(
    image_bytes: bytes,
    filename: str,
    language: str = DEFAULT_LANG,
    api_key: Optional[str] = None,
    create_searchable_pdf: bool = False,
) -> OcrFullResult:
    result = call_ocr_space(
        file_bytes=image_bytes,
        filename=filename,
        language=language,
        api_key=api_key,
        create_searchable_pdf=create_searchable_pdf,
    )
    parsed = result.get("ParsedResults") or []
    text = ""
    searchable_pdf_urls: List[str] = []
    if parsed:
        text = parsed[0].get("ParsedText", "") or ""
        for p in parsed:
            if p.get("SearchablePDFURL"):
                searchable_pdf_urls.append(p["SearchablePDFURL"])

    return OcrFullResult(
        pages=1,
        text_per_page=[text],
        merged_text=f"--- Página 1 ---\n{text}".rstrip(),
        json_pages=[result],
        searchable_pdf_urls=searchable_pdf_urls,
    )

# ---------------------------------------------------------------------
# Función principal para tu vista Streamlit
# ---------------------------------------------------------------------
def process_pdf_or_image(
    file_bytes: bytes,
    filename: str,
    language: str = DEFAULT_LANG,
    api_key: Optional[str] = None,
    create_searchable_pdf: bool = False,
    max_pages_per_call: int = DEFAULT_MAX_PAGES_PER_CALL,
) -> OcrFullResult:
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        return ocr_pdf_with_fallback(
            pdf_bytes=file_bytes,
            filename=filename,
            language=language,
            api_key=api_key,
            create_searchable_pdf=create_searchable_pdf,
            max_pages_per_call=max_pages_per_call,
        )
    else:
        return ocr_image(
            image_bytes=file_bytes,
            filename=filename,
            language=language,
            api_key=api_key,
            create_searchable_pdf=create_searchable_pdf,
        )

# ---------------------------------------------------------------------
# Helpers para Streamlit (renderizar y descargas)
# ---------------------------------------------------------------------
def build_txt_bytes(full_text: str) -> bytes:
    return full_text.encode("utf-8")

def build_json_bytes(result: OcrFullResult) -> bytes:
    payload = {
        "pages": result.pages,
        "text_per_page": result.text_per_page,
        "searchable_pdf_urls": result.searchable_pdf_urls,
        "json_pages": result.json_pages,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

def render_results_in_streamlit(st, result: OcrFullResult, base_filename: str):
    """
    Dibuja componentes típicos: conteo de páginas, texto por página, botones de descarga.
    """
    st.write("**Páginas detectadas:**", result.pages)
    st.write("**URLs de PDF buscable:**", len(result.searchable_pdf_urls))
    with st.expander("Texto por página", expanded=(result.pages <= 3)):
        for i, t in enumerate(result.text_per_page, start=1):
            st.markdown(f"**Página {i}**")
            st.text(t if t.strip() else "[vacío]")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "⬇️ Descargar TXT",
            data=build_txt_bytes(result.merged_text),
            file_name=f"{base_filename}.txt",
            mime="text/plain",
        )
    with col2:
        st.download_button(
            "⬇️ Descargar JSON",
            data=build_json_bytes(result),
            file_name=f"{base_filename}.json",
            mime="application/json",
        )

    if result.searchable_pdf_urls:
        st.info("PDF(s) buscable(s) generados por el servicio (pueden tener marca de agua en plan gratuito):")
        for i, url in enumerate(result.searchable_pdf_urls, start=1):
            st.markdown(f"- **PDF buscable {i}:** {url}")
