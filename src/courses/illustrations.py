"""Affichage des seules zones source enregistrées dans les fiches."""

import hashlib
from pathlib import Path

import pymupdf

from src.config import COURSE_PDF_DIR
from src.courses.service import load_course
from src.models.card import CardCollection
from src.storage.course_repository import CourseRepository


def render_card_illustration(course_id: str, card_id: str, index: int) -> bytes:
    course = load_course(course_id)
    collection = CardCollection.model_validate(CourseRepository().load_cards(course_id))
    card = next((c for c in collection.cards if c.card_id == card_id), None)
    if card is None or not 0 <= index < len(card.illustrations):
        raise FileNotFoundError("Illustration introuvable")
    filename = course["source_filename"]
    if Path(filename).name != filename:
        raise ValueError("Nom du PDF invalide")
    path = COURSE_PDF_DIR / filename
    if collection.file_hash != course["file_hash"] or hashlib.sha256(path.read_bytes()).hexdigest() != course["file_hash"]:
        raise ValueError("Le PDF ne correspond plus à la fiche")
    source = card.illustrations[index]
    with pymupdf.open(path) as document:
        if source.page > len(document):
            raise ValueError("Page source invalide")
        page = document[source.page - 1]
        bbox = pymupdf.Rect(source.bbox)
        if not page.rect.contains(bbox):
            raise ValueError("Zone hors de la page source")
        # Résolution lisible et bornée, sans fichier dérivé à synchroniser.
        scale = min(2.0, 1800 / max(bbox.width, bbox.height))
        return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=bbox, alpha=False).tobytes("png")
