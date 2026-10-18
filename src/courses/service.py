"""Orchestration des cours StudyPilot.

Le service expose une API métier simple aux routes Flask : catalogue, cours,
plan et création. Les données actives vivent dans ``data/courses/<course_id>/``.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
import unicodedata

from pydantic import ValidationError

from src.config import COURSE_DATA_DIR, COURSE_PDF_DIR, STUDY_MODEL
from src.courses.plan_manager import (
    build_candidate,
    load_plan_file,
    overview_summary,
    plan_paths,
    save_plan_file,
    validate_candidate,
)
from src.courses.planner import extract_document, generate_overviews, preview_snapshot
from src.models.course import CourseRecord
from src.models.plan import CoursePlan
from src.storage.course_repository import CourseRepository
from src.storage.repository import StorageError
from src.models.card import CardCollection
from src.courses.card_presentation import publication_issue, present_card, publication_view


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return slug[:60] or "cours"


def make_course_id(title: str, file_hash: str) -> str:
    """Construit l'identifiant stable d'un cours à partir de son titre et du PDF."""
    return f"{_slug(title)}-{file_hash[:10]}"


def _repository() -> CourseRepository:
    return CourseRepository(COURSE_DATA_DIR)


def _canonical_plan(plan: dict, course_id: str) -> dict:
    """Ajoute l'enveloppe commune sans muter le plan de travail."""
    result = deepcopy(plan)
    result["schema_version"] = 1
    result["course_id"] = course_id
    return result


def _source_filename(course: dict) -> str:
    return str(course.get("source_filename") or course.get("filename") or "").strip()


def _validated_plan(course: dict, plan: dict) -> dict | None:
    """Valide un plan avec le schéma Pydantic et les métadonnées du cours."""
    pdf_name = _source_filename(course)
    course_id = str(course.get("course_id") or "").strip()
    if not course_id:
        title = str(course.get("title") or "").strip()
        file_hash = str(course.get("file_hash") or "")
        if not title or len(file_hash) < 32:
            return None
        course_id = make_course_id(title, file_hash)

    if (
        plan.get("plan_version") != 1
        or plan.get("filename") != pdf_name
        or plan.get("file_hash") != course.get("file_hash")
        or plan.get("page_count") != course.get("page_count")
    ):
        return None

    candidate = deepcopy(plan)
    candidate.setdefault("schema_version", 1)
    candidate.setdefault("course_id", course_id)
    try:
        validated = CoursePlan.model_validate(candidate)
    except ValidationError:
        return None
    return validated.model_dump(mode="json")


def load_course(course_id: str) -> dict:
    """Charge et valide les métadonnées canoniques d'un cours."""
    safe_id = CourseRepository.validate_course_id(course_id)
    try:
        raw = _repository().load_course(safe_id)
        record = CourseRecord.model_validate(raw)
    except (StorageError, ValidationError) as error:
        raise FileNotFoundError(safe_id) from error
    return record.model_dump(mode="json")


def load_course_plan(course: dict) -> dict | None:
    """Charge le plan canonique d'un cours et vérifie sa cohérence avec le PDF."""
    course_id = str(course.get("course_id") or "")
    try:
        safe_id = CourseRepository.validate_course_id(course_id)
    except ValueError:
        return None

    pdf_name = _source_filename(course)
    if (
        not pdf_name
        or Path(pdf_name).name != pdf_name
        or not pdf_name.lower().endswith(".pdf")
        or not (COURSE_PDF_DIR / pdf_name).is_file()
    ):
        return None

    try:
        plan = _repository().load_plan(safe_id)
    except StorageError:
        return None
    return _validated_plan(course, plan)



def _reviewed_collection(course):
    from src.courses.reviewed import load_reviewed
    cid = CourseRepository.validate_course_id(str(course.get('course_id') or ''))
    return load_reviewed(course, load_course_plan(course), _repository().paths(cid).root, COURSE_PDF_DIR)


def load_part_cards(course: dict, part_id: str) -> list[dict]:
    """Fiches validées générées et compléments relus, sans modifier les caches."""
    from src.courses.study_guide import load_guide, part_cards
    guide = load_guide(course)
    if guide is not None:
        return part_cards(guide, part_id)
    try:
        cid = CourseRepository.validate_course_id(str(course.get('course_id') or ''))
    except ValueError:
        return []
    reviewed = _reviewed_collection(course)
    manual = reviewed.cards if reviewed is not None else []
    covered = {c.concept_id for c in manual} | {i for c in manual for i in c.covered_concept_ids}
    try:
        collection = publication_view(CardCollection.model_validate(_repository().load_cards(cid)))
        generated = collection.cards if collection.file_hash == course.get('file_hash') else []
        from src.storage.repository import read_json
        try:
            preparation = read_json(_repository().paths(cid).root / 'pedagogy.json')
        except StorageError:
            preparation = {}
        fully_generated = (bool(collection.parts) and all(p.status == 'complete' for p in collection.parts)
            and not (collection.blocked or collection.failures or collection.review_issues or collection.unreviewed_cards)
            and preparation.get('stage') == 'prepared' and preparation.get('fingerprint') == collection.quality_hash)
        if reviewed is not None and reviewed.coverage=='course_review':
            generated=[]
        elif fully_generated:
            manual = []
            covered = set()
    except (StorageError, ValidationError):
        generated = []
    result = []
    for card in manual + [c for c in generated if c.concept_id not in covered]:
        if (card.primary_part_id == part_id or part_id in card.related_part_ids) and not publication_issue(card):
            data = present_card(card)
            data['review_provenance'] = 'editorial_review' if card in manual else 'model_generation'
            result.append(data)
    return result


def load_part_unavailable(course: dict, part_id: str) -> list[dict]:
    from src.courses.study_guide import load_guide
    guide = load_guide(course)
    if guide is not None:
        state = next((p for p in guide['parts'] if p['part_id'] == part_id), None)
        if state and state['status'] == 'complete':
            return []
        return [dict(title='Préparation des fiches', reason=reason) for reason in
                (state or {}).get('errors', ['Traitement à reprendre.'])]
    reviewed = _reviewed_collection(course)
    if reviewed is not None and reviewed.coverage=='course_review':
        # Le jeu relu couvre le contenu du PDF. Les erreurs du générateur
        # restent dans ses diagnostics ; elles ne sont pas des fiches manquantes
        # dans cet ensemble disponible.
        return []
    covered = ({c.concept_id for c in reviewed.cards} | {i for c in reviewed.cards for i in c.covered_concept_ids}) if reviewed else set()
    try:
        collection = CardCollection.model_validate(_repository().load_cards(
            CourseRepository.validate_course_id(str(course.get("course_id") or ""))))
    except (ValueError, StorageError, ValidationError):
        return []
    if collection.file_hash != course.get("file_hash"):
        return []
    collection = publication_view(collection)
    items = {c.concept_id: {"title": c.title, "reason": c.reason}
             for c in collection.blocked + collection.failures if c.primary_part_id == part_id and c.concept_id not in covered}
    for card in collection.cards:
        if card.concept_id not in covered and card.primary_part_id == part_id and (issue := publication_issue(card)):
            items[card.concept_id] = {"title": card.title, "reason": issue}
    for number, issue in enumerate(collection.review_issues):
        if issue.get("concept_id") in covered:
            continue
        from src.courses.pedagogy import issue_affects_part
        if issue_affects_part(issue, part_id):
            items['review-' + str(number)] = {'title': issue.get('title', 'Couverture du cours'),
                                           'status': issue['status'], 'reason': issue['reason']}
    state = next((p for p in collection.parts if p.part_id == part_id), None)
    if not items and state is not None and state.status != 'complete':
        items['pending'] = {'title': 'Traitement à reprendre', 'status': 'review_pending',
                            'reason': state.message or 'Cette partie n’a pas encore terminé ses contrôles.'}
    return list(items.values())


def load_part_ignored(course: dict, part_id: str) -> list[dict]:
    """Mentions écartées, conservées dans le diagnostic de leur partie."""
    from src.courses.study_guide import load_guide
    guide = load_guide(course)
    if guide is not None:
        return [dict(title='Passage source', reason=d['reason']) for d in guide.get('decisions', [])
                if d.get('part_id') == part_id and not d.get('entry_keys')]
    reviewed = _reviewed_collection(course)
    if reviewed is not None and reviewed.coverage=='course_review':
        return []
    try:
        course_id = CourseRepository.validate_course_id(str(course.get("course_id") or ""))
        collection = CardCollection.model_validate(_repository().load_cards(course_id))
    except (ValueError, StorageError, ValidationError):
        return []
    if collection.file_hash != course.get("file_hash"):
        return []
    return [c.model_dump(mode="json") for c in collection.ignored if c.primary_part_id == part_id]


def find_course(query: str) -> dict:
    """Résout un cours par identifiant, titre ou nom de PDF.

    La recherche accepte un fragment tant qu'il correspond à un seul cours.
    """
    value = str(query).strip().casefold()
    if not value:
        raise ValueError("Le nom du cours est vide.")

    matches = []
    for course in list_courses():
        haystacks = (
            str(course.get("course_id") or "").casefold(),
            str(course.get("title") or "").casefold(),
            str(course.get("source_filename") or "").casefold(),
            str(course.get("original_filename") or "").casefold(),
        )
        if any(value in item for item in haystacks):
            matches.append(course)

    if not matches:
        raise ValueError(f"Aucun cours ne correspond à {query!r}.")
    if len(matches) > 1:
        names = ", ".join(str(item.get("title") or item.get("course_id")) for item in matches)
        raise ValueError(f"Recherche ambiguë pour {query!r} : {names}.")
    return matches[0]


def list_courses() -> list[dict]:
    """Retourne le catalogue actif à partir du stockage canonique uniquement."""
    repository = _repository()
    courses: list[dict] = []

    for course_id in repository.list_course_ids():
        try:
            course = load_course(course_id)
        except (FileNotFoundError, ValueError):
            continue
        plan = load_course_plan(course)
        course["part_count"] = len(plan["parts"]) if plan is not None else 0
        course["plan_available"] = plan is not None
        courses.append(course)

    return sorted(courses, key=lambda item: str(item.get("title") or "").casefold())



def _save_canonical_course(record: CourseRecord) -> None:
    _repository().save_course(record.course_id, record.model_dump(mode="json"))


def _save_canonical_plan(course_id: str, plan: dict) -> None:
    _repository().save_plan(course_id, _canonical_plan(plan, course_id))


def create_course(
    pdf_path: str | Path,
    *,
    title: str,
    original_filename: str,
    model: str = STUDY_MODEL,
    progress_callback=None,
) -> dict:
    """Crée un cours et son plan moderne à partir d'un PDF déjà validé."""
    pdf = Path(pdf_path)
    if not pdf.is_file() or pdf.parent != COURSE_PDF_DIR:
        raise ValueError("Le PDF doit provenir du dossier de cours validé.")

    document = extract_document(pdf)
    active_path, candidate_path = plan_paths(pdf)

    if candidate_path.is_file():
        candidate = load_plan_file(candidate_path)
        plan = validate_candidate(candidate, pdf, document)
    else:
        candidate = build_candidate(pdf, document)
        candidate["model"] = model
        candidate["consolidation"] = {
            "version": 1,
            "origin": "automatic_import",
            "review_required": False,
        }
        save_plan_file(candidate_path, candidate)
        plan = validate_candidate(candidate, pdf, document)

    now = datetime.now(timezone.utc).isoformat()
    course_id = make_course_id(title, document["file_hash"])
    record = CourseRecord(
        course_id=course_id,
        title=title,
        source_filename=pdf.name,
        file_hash=document["file_hash"],
        page_count=document["page_count"],
        original_filename=original_filename,
        uploaded_at=now,
    )
    _save_canonical_course(record)

    # Le plan structurel validé est disponible immédiatement, même si les
    # vues d'ensemble sont interrompues ensuite.
    initial_snapshot = preview_snapshot(plan)
    save_plan_file(active_path, initial_snapshot)
    _save_canonical_plan(course_id, initial_snapshot)

    completed = sum(
        part.get("overview", {}).get("status") in ("draft", "not_applicable")
        for part in plan["parts"]
    )
    total = len(plan["parts"])

    def checkpoint(current: dict, part: dict) -> None:
        nonlocal completed
        snapshot = preview_snapshot(current)
        snapshot["consolidation"] = {
            "version": 1,
            "origin": "automatic_import",
            "review_required": False,
        }
        save_plan_file(candidate_path, snapshot)
        save_plan_file(active_path, snapshot)
        _save_canonical_plan(course_id, snapshot)
        completed = sum(
            item.get("overview", {}).get("status") in ("draft", "not_applicable")
            for item in snapshot["parts"]
        )
        if progress_callback is not None:
            progress_callback(completed, total, str(part.get("number") or ""), "overview")

    if progress_callback is not None:
        progress_callback(completed, total, "", "plan")

    generate_overviews(plan, document, model=model, progress_callback=checkpoint)

    snapshot = preview_snapshot(plan)
    snapshot["consolidation"] = {
        "version": 1,
        "origin": "automatic_import",
        "review_required": False,
    }
    save_plan_file(candidate_path, snapshot)
    save_plan_file(active_path, snapshot)
    _save_canonical_plan(course_id, snapshot)

    counts = overview_summary(snapshot)
    incomplete = counts["pending"] + counts["error"]
    from src.courses.pipeline import process_course
    study = process_course(course_id, model=model, progress_callback=progress_callback)
    incomplete += study["incomplete"]
    return {
        "status": "ready" if incomplete == 0 else "partial",
        "course_id": course_id,
        "done": counts["draft"] + counts["not_applicable"],
        "total": len(snapshot["parts"]),
        "incomplete": incomplete,
        "plan": snapshot,
        "study": study,
    }



def refresh_overviews(course_id: str, *, model=STUDY_MODEL, progress_callback=None) -> dict:
    """Met à niveau les aperçus existants sans reconstruire plan, inventaire ou fiches."""
    from src.courses.planner import restore_preview
    from src.courses.overview import is_current
    from src.courses.pedagogy import backup
    course = load_course(course_id)
    saved = load_course_plan(course)
    if not saved:
        raise ValueError('Plan indisponible.')
    pdf = COURSE_PDF_DIR / course['source_filename']
    document = extract_document(pdf)
    plan = restore_preview(saved, document)
    if all(is_current(p.get('overview', {})) for p in plan['parts']):
        return dict(status='ready', updated=0)
    backup(_repository().paths(course_id).plan, 'before_overview_upgrade')
    mirrors = []
    for path in plan_paths(pdf):
        if not path.is_file():
            continue
        existing = load_plan_file(path)
        if (existing.get('file_hash') == saved['file_hash']
                and [p['id'] for p in existing.get('parts', [])] == [p['id'] for p in saved['parts']]):
            backup(path, 'before_overview_upgrade')
            mirrors.append((path, existing))
    updated = 0

    def checkpoint(active, part):
        nonlocal updated
        overview = part['overview']
        if overview.get('status') == 'error' and overview.get('previous'):
            part['overview'] = dict(overview['previous'], refresh_error=overview['message'])
        elif is_current(overview):
            updated += 1
        _save_canonical_plan(course_id, preview_snapshot(active))
        for path, mirror in mirrors:
            target = next(p for p in mirror['parts'] if p['id'] == part['id'])
            target['overview'] = part['overview']
            save_plan_file(path, mirror)
        if progress_callback:
            progress_callback(part)

    # Un même extracteur sert à l'import et à la mise à niveau des anciens cours.
    generate_overviews(plan, document, model=model, progress_callback=checkpoint)
    return dict(status='ready' if all(is_current(p['overview']) for p in plan['parts']) else 'partial', updated=updated)


def canonical_storage_status() -> list[dict]:
    """Retourne un résumé lisible du stockage par cours."""
    repository = _repository()
    result: list[dict] = []
    for course_id in repository.list_course_ids():
        paths = repository.paths(course_id)
        try:
            course = load_course(course_id)
        except (FileNotFoundError, ValueError):
            continue
        result.append(
            {
                "course_id": course_id,
                "title": course.get("title") or course_id,
                "has_plan": paths.plan.is_file(),
                "has_inventory": paths.inventory.is_file(),
                "has_cards": paths.cards.is_file(),
            }
        )
    return result
