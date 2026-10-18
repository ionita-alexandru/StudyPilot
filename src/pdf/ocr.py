"""Lecture des images sans remplacer le texte natif du PDF."""

from __future__ import annotations

import os
from collections import OrderedDict

import pymupdf

from src.config import PROJECT_ROOT

_OCR_CACHE: OrderedDict = OrderedDict()


def _text_lines(blocks: list[dict], *, ocr_only: bool = False) -> list[dict]:
    result = []
    for block in blocks:
        for line in block.get("lines", []):
            spans = line["spans"]
            if ocr_only:
                spans = [s for s in spans if s.get("font") == "GlyphLessFont"]
            text = "".join(s["text"] for s in spans).strip()
            if text:
                result.append({
                    "text": text, "bbox": list(line["bbox"]), "ocr": ocr_only,
                    "size": max((s.get("size", 0) for s in spans), default=0),
                    "bold_text": "".join(s["text"] for s in spans if s.get("flags", 0) & 16),
                })
    return result


def extract_page_sources(page, *, file_hash: str | None = None) -> dict:
    raw = page.get_text("text", sort=False)
    native = page.get_text("dict")
    lines = _text_lines(native["blocks"])
    has_images = any(b.get("type") == 1 for b in native["blocks"])
    ocr_lines = []
    if has_images:
        language = os.getenv("STUDYPILOT_OCR_LANGUAGE", "eng")
        configured = os.getenv("STUDYPILOT_TESSDATA")
        local = PROJECT_ROOT / "data" / "ocr" / "tessdata"
        tessdata = configured or (str(local) if local.is_dir() else None)
        key = ("image-resolution-v2", file_hash, page.number, language, tessdata)
        if file_hash and key in _OCR_CACHE:
            ocr_lines = _OCR_CACHE[key]
            _OCR_CACHE.move_to_end(key)
        else:
            try:
                images = [b for b in native["blocks"] if b.get("type") == 1]
                if all("image" in b and "transform" in b for b in images):
                    ocr_lines = _image_lines(images, language=language, tessdata=tessdata)
                else:
                    textpage = page.get_textpage_ocr(
                        language=language, dpi=300, full=False, tessdata=tessdata,
                    )
                    ocr_lines = _text_lines(
                        page.get_text("dict", textpage=textpage)["blocks"], ocr_only=True,
                    )
            except (RuntimeError, ValueError, pymupdf.mupdf.FzErrorBase) as error:
                raise ValueError(
                    f"OCR indisponible à la page {page.number + 1}. "
                    "Place les fichiers de langue Tesseract dans data/ocr/tessdata "
                    "ou définis STUDYPILOT_TESSDATA. "
                    f"Langue demandée : {language}. Détail : {error}"
                ) from error
            if file_hash:
                _OCR_CACHE[key] = ocr_lines
                if len(_OCR_CACHE) > 64:
                    _OCR_CACHE.popitem(last=False)
    # L'OCR partiel est ajouté en fin de page par PyMuPDF. Sa position
    # physique permet de le rattacher au bon titre, avant la section suivante.
    ordered = sorted(lines + ocr_lines, key=lambda item: (item["bbox"][1], item["bbox"][0]))
    return {
        "raw_text": raw, "native": native, "lines": ordered,
        "ocr_used": has_images, "ocr_text": "\n".join(i["text"] for i in ocr_lines),
    }


def _image_lines(images, *, language, tessdata):
    """OCR des pixels avec résolution suffisante puis retour aux coordonnées PDF.

    Le dpi de get_textpage_ocr(full=False) ne redimensionne pas les images.
    Les petites captures restent donc peu lisibles sans cette étape explicite.
    """
    result = []
    for block in images:
        bbox = pymupdf.Rect(block["bbox"])
        if bbox.width <= 3 or bbox.height <= 3:
            continue
        pix = pymupdf.Pixmap(block["image"])
        if min(pix.width, pix.height) < 3:
            # Traits/décorations isolés : illisibles pour Tesseract. Les pixels
            # restent présents dans le PDF et dans les extraits visuels.
            continue
        if pix.n - pix.alpha != 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        if pix.alpha:
            pix = pymupdf.Pixmap(pix, 0)
        # Ne pas faire exploser la mémoire sur les grands scans.
        effective_dpi = min(pix.width / bbox.width, pix.height / bbox.height) * 72
        if effective_dpi < 180 and pix.width * pix.height <= 1_000_000:
            pix = pymupdf.Pixmap(pix, pix.width * 2, pix.height * 2, None)
        data = pix.pdfocr_tobytes(language=language, tessdata=tessdata)
        with pymupdf.open("pdf", data) as document:
            ocr_page = document[0]
            matrix = pymupdf.Matrix(1 / ocr_page.rect.width, 1 / ocr_page.rect.height) * pymupdf.Matrix(block["transform"])
            for line in _text_lines(ocr_page.get_text("dict")["blocks"], ocr_only=True):
                line["bbox"] = list(pymupdf.Rect(line["bbox"]) * matrix)
                result.append(line)
    return result
