"""Outils légers de recherche textuelle dans les PDF StudyPilot."""

from __future__ import annotations

import re
import unicodedata


_STOP_WORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "et", "ou", "a", "au",
    "aux", "en", "dans", "sur", "pour", "par", "avec", "sans", "ce", "ces", "cette", "cet",
    "est", "sont", "etre", "qui", "que", "quoi", "comment", "pourquoi", "quel", "quelle",
    "quels", "quelles", "je", "tu", "il", "elle", "nous", "vous", "ils", "elles", "me", "m",
    "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses", "c", "ca", "ça", "fait",
}


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFD", str(text).lower())
    text = "".join(character for character in text if unicodedata.category(character) != "Mn")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_words(text: str) -> set[str]:
    return {
        word for word in normalize_text(text).split()
        if len(word) >= 3 and word not in _STOP_WORDS
    }


def extract_main_concept(question: str) -> set[str]:
    normalized = normalize_text(question)
    for pattern in (
        "c est quoi", "qu est ce que", "que signifie", "a quoi sert", "comment faire",
        "comment calculer", "comment trouver", "comment determiner", "comment savoir",
        "comment utiliser", "explique moi", "peux tu expliquer", "pourquoi utiliser",
        "pourquoi on utilise",
    ):
        normalized = normalized.replace(pattern, " ")
    return extract_words(normalized)


def split_into_chunks(text: str, chunk_size: int = 900, overlap: int = 150) -> list[str]:
    """Découpe du texte en passages chevauchants sans couper trop brutalement les phrases."""
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", str(text))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            search_start = max(start, end - 200)
            sentence_end = max(
                text.rfind(".", search_start, end),
                text.rfind("?", search_start, end),
                text.rfind("!", search_start, end),
            )
            if sentence_end > start:
                end = sentence_end + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        new_start = max(0, end - overlap)
        start = end if new_start <= start else new_start
    return chunks
