"""Détection de sections avec conservation des pages sources.

Ne saute jamais une ligne du cours sous prétexte qu'elle ressemble à la suite
possible d'un titre. Compatible avec les champs historiques `content`,
`number`, `title` et `page_start`.
"""

import re

PARSER_VERSION = 3

NUMBER_ONLY = re.compile(r"^\d+\.\d+(?:\.\d+)*\.?$")
NUMBER_AND_TITLE = re.compile(r"^(\d+\.\d+(?:\.\d+)*)\.?\s+(.+)$")
PAGE_HEADER = re.compile(r"^\d+\.\d+(?:\.\d+)*\.\s+[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ\s\-’']{6,}$")
NOT_TITLE = re.compile(
    r"^(?:définition|théorème|theoreme|propriété|proposition|lemme|"
    r"exemple|exercice|remarque|soit\b|dans\s+ce\b|dans\s+tout\b|"
    r"on\s+appelle\b|pour\s+tout\b|il\s+existe\b)",
    re.IGNORECASE,
)


def is_section_number(line: str) -> bool:
    return bool(NUMBER_ONLY.fullmatch(line.strip()))


def is_page_header(line: str) -> bool:
    return bool(PAGE_HEADER.fullmatch(line.strip()))


def _new_section(number: str, title: str, page: int) -> dict:
    return {
        "number": number,
        "title": title or f"Section {number}",
        "page_start": page,
        "content": "",
        "content_pages": [],
    }


def _append_line(section: dict, page: int, line: str) -> None:
    if not section["content_pages"] or section["content_pages"][-1]["page"] != page:
        section["content_pages"].append({"page": page, "text": ""})
    section["content_pages"][-1]["text"] += line + "\n"


def _finish(section: dict) -> dict:
    for span in section["content_pages"]:
        span["text"] = span["text"].strip()
    section["content_pages"] = [span for span in section["content_pages"] if span["text"]]
    section["content"] = "\n".join(span["text"] for span in section["content_pages"])
    return section


def _can_be_title(line: str) -> bool:
    """Heuristique conservatrice : en cas de doute, la ligne reste du contenu."""
    if not line or is_section_number(line) or is_page_header(line):
        return False
    if NOT_TITLE.match(line) or len(line) > 110:
        return False
    if re.search(r"[=∈∀∃⇔⇒;:]", line):
        return False
    # Un point final après une phrase longue indique souvent le début du cours.
    if line.endswith(".") and len(line.split()) > 10:
        return False
    return True


def extract_sections(pages: list[dict]) -> list[dict]:
    sections: list[dict] = []
    current: dict | None = None

    for page in pages:
        page_number = int(page["page"])
        lines = str(page.get("text", "")).splitlines()
        index = 0

        while index < len(lines):
            line = lines[index].strip()
            if not line or is_page_header(line):
                index += 1
                continue

            number: str | None = None
            title = ""
            consumed = 1

            if is_section_number(line):
                number = line.rstrip(".")
                # Une seule ligne est prise comme titre, jamais deux par défaut.
                if index + 1 < len(lines):
                    candidate = lines[index + 1].strip()
                    if _can_be_title(candidate):
                        title = candidate
                        consumed = 2
            else:
                inline = NUMBER_AND_TITLE.fullmatch(line)
                if inline and _can_be_title(inline.group(2)):
                    number = inline.group(1)
                    title = inline.group(2)

            if number is not None:
                if current is not None:
                    sections.append(_finish(current))
                current = _new_section(number, title, page_number)
                index += consumed
                continue

            if current is not None:
                _append_line(current, page_number, line)
            index += 1

    if current is not None:
        sections.append(_finish(current))

    # Certains PDF (histoire, cours en prose, supports courts) n'ont aucun titre
    # numérique reconnu. On ne doit pas perdre tout leur contenu.
    if not sections:
        # Un diaporama (CSS, histoire, etc.) n'a pas de numérotation 2.1.
        # Le répartir en blocs de 4 pages évite une fiche unique de 26 pages.
        # Ces titres sont descriptifs, pas une fausse classification sémantique.
        for start in range(0, len(pages), 4):
            chunk = pages[start:start + 4]
            first, last = int(chunk[0]["page"]), int(chunk[-1]["page"])
            title = f"Pages {first} à {last}" if first != last else f"Page {first}"
            fallback = _new_section(str(len(sections) + 1), title, first)
            for page in chunk:
                for line in str(page.get("text", "")).splitlines():
                    if line.strip():
                        _append_line(fallback, int(page["page"]), line.strip())
            if fallback["content_pages"]:
                sections.append(_finish(fallback))

    return sections
