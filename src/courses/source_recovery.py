"""Récupération bornée du contexte et des images, indépendante de la matière."""

import re

from src.models.concept import ConceptEvidence, SourceIllustration


def label(value):
    return re.sub(r"\s+", " ", value).strip(" •▪◦\uf097:?\n\t").casefold()


def _meaningful_lines(text):
    return [line.strip() for line in text.splitlines() if label(line)]


def _region(page, start, end):
    images = [b for b in page.get("image_regions", []) if b[1] >= start - 2 and b[3] <= end + 2]
    if not images:
        return None
    # La capture conserve aussi les légendes natives entre les images.
    rect = page["page_rect"]
    return [max(rect[0], min(b[0] for b in images) - 2),
            max(rect[1], min(b[1] for b in images) - 2),
            min(rect[2], max(b[2] for b in images) + 2),
            min(rect[3], max(b[3] for b in images) + 2)]


def attach_illustrations(pages):
    """Associe les images à un titre explicite, sans interpréter les pixels."""
    for page in pages:
        units = page.get("source_units", [])
        height = page.get("page_rect", [0, 0, 0, 0])[3]
        for i, unit in enumerate(units):
            if not unit["heading"] or "y" not in unit:
                continue
            # Une frontière de sous-rubrique borne également la capture.
            end = units[i + 1].get("y", height) if i + 1 < len(units) else height
            bbox = _region(page, unit["y"], end)
            if bbox:
                unit["illustrations"] = [dict(page=page["page"], anchor_page=page["page"],
                                               heading=unit["heading"], bbox=bbox)]
    for left, right in zip(pages, pages[1:]):
        if right["page"] != left["page"] + 1 or not left.get("source_units"):
            continue
        last = left["source_units"][-1]
        units = right.get("source_units", [])
        first = units[0] if units else {}
        height = left.get("page_rect", [0, 0, 0, 0])[3]
        # Un titre isolé en bas de page, suivi d'images avant le prochain titre.
        # La présence de prose native ou d'un nouveau titre interdit ce lien.
        if (not last["heading"] or label(last["excerpt"]) != label(last["heading"])
                or not height or last.get("y", 0) < height * .65
                or (not first.get("heading") and _meaningful_lines(first.get("native_text", "")))):
            continue
        end = (first.get("y", 0) if first.get("heading") else
               units[1].get("y", 0) if len(units) > 1 else right["page_rect"][3])
        bbox = _region(right, 0, end)
        if bbox:
            last["illustrations"] = [dict(page=right["page"], anchor_page=left["page"],
                                           heading=last["heading"], bbox=bbox)]


def _matches(concept, unit):
    heading = label(unit["heading"])
    anchors = [concept.source_anchor or "", concept.title]
    # Une preuve enrichie peut déjà contenir le titre suivi des étiquettes OCR.
    # Son premier intitulé reste l'ancre ; ne pas comparer tout le bloc au titre.
    anchors.extend(lines[0] for e in concept.evidence if (lines := _meaningful_lines(e.excerpt)))
    if heading and any(label(a) == heading for a in anchors):
        return True
    # Un identifiant technique exact ne peut pas être remplacé par son voisin.
    names = re.findall(r"\b[A-Za-z][\w]*(?:-[\w]+)+\b", concept.title)
    return len(set(names)) == 1 and bool(re.search(r"(?<![\w-])" + re.escape(names[0]) + r"(?![\w-])", unit["heading"]))


def illustration_candidates(concept, pages):
    return [SourceIllustration.model_validate(image)
            for page in pages if page["page"] in concept.source_pages
            for unit in page.get("source_units", []) if _matches(concept, unit)
            for image in unit.get("illustrations", [])]


def illustrations_supported(concept, pages):
    available = illustration_candidates(concept, pages)
    if concept.learning_points:
        from src.courses.pedagogy import visual_sources
        try:
            available.extend(visual_sources(concept, [p.model_dump() for p in concept.learning_points], {'pages': pages}))
        except (ValueError, KeyError):
            pass
    page_map = {p["page"]: p for p in pages}
    return bool(concept.illustrations) and all(
        image.page in page_map and image.anchor_page in page_map and (
            image in available or (
                image.origin == "page" and concept.card_role == "visual" and image.page == image.anchor_page
                and list(image.bbox) == list(page_map[image.page].get("page_rect", []))
                and any(e.page == image.page for e in concept.evidence)
                and image.heading == (concept.source_anchor or concept.title)
            )) for image in concept.illustrations
    )


def list_context(concept, pages):
    """Retrouve la phrase explicative d'une liste, pas une simple énumération."""
    from src.courses.inventory import _excerpt_is_grounded
    candidates = []
    for evidence in concept.evidence:
        target = label(evidence.excerpt)
        if len(target.split()) > 3 or not target or "\n" in target:
            continue
        for page in pages:
            if page["page"] != evidence.page:
                continue
            for unit in page.get("source_units", []):
                lines = unit["excerpt"].splitlines()
                hits = [i for i, line in enumerate(lines) if label(line) == target]
                if len(hits) != 1:
                    continue
                end = hits[0]
                target_lines = [l for l in unit.get("native_lines", []) if label(l["text"]) == target]
                if len(target_lines) != 1:
                    continue
                for start in range(end - 1, -1, -1):
                    line = lines[start].strip()
                    if not label(line):
                        continue
                    if len(label(line).split()) <= 3:
                        continue
                    # Une phrase d'au moins six mots doit introduire la liste.
                    # Les titres, snippets et le corps d'un autre item sont exclus.
                    if (len(label(line).split()) >= 6 and label(line) != label(unit["heading"])
                            and not re.search(r"[{};=<>]", line)
                            and any(label(l["text"]) == label(line)
                                    and l["bbox"][0] + 8 < target_lines[0]["bbox"][0]
                                    for l in unit.get("native_lines", []))
                            and all(len(label(l).split()) <= 3 for l in lines[start + 1:end])):
                        literal = "\n".join(lines[start:end + 1]).strip()
                        prefix = "\n".join(lines[:start]).strip()
                        if unit["heading"] and len(prefix) <= 250:
                            literal = "\n".join(lines[:end + 1]).strip()
                        if len(literal) <= 1200 and _excerpt_is_grounded(literal, page):
                            candidates.append(ConceptEvidence(page=page["page"], excerpt=literal))
                    break
    # Deux introductions possibles signifient que l'association est ambiguë.
    unique = list({(e.page, e.excerpt): e for e in candidates}.values())
    return unique if len(unique) == 1 else []


def recover_document_evidence(concept, pages):
    from src.courses.inventory import concept_evidence_issue, refresh_concept_evidence
    own = [p for p in pages if p["page"] in concept.source_pages]
    if concept.illustrations and not concept_evidence_issue(concept, own):
        return concept.model_copy(update={"evidence_issue": None})
    updated = refresh_concept_evidence(concept, own)
    if not updated.evidence_issue:
        return updated
    context = list_context(updated, own)
    if context and updated.evidence_issue.startswith("preuves limitées"):
        candidate = updated.model_copy(update={"evidence": context})
        if not concept_evidence_issue(candidate, own):
            return candidate.model_copy(update={"evidence_issue": None})
    images = illustration_candidates(updated, own)
    if len(images) != 1:
        return updated
    image = images[0]
    # Seul le titre littéral de l'unité atteste le rattachement de l'image.
    evidence = [ConceptEvidence(page=image.anchor_page, excerpt=image.heading)]
    candidate = updated.model_copy(update={"evidence": evidence, "illustrations": images,
        "source_pages": sorted(set(updated.source_pages + [image.page, image.anchor_page]))})
    issue = concept_evidence_issue(candidate, [p for p in pages if p["page"] in candidate.source_pages])
    return candidate.model_copy(update={"evidence_issue": issue}) if not issue else updated
