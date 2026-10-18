"""Gestion du cycle de vie d'un plan de cours.

Ce module gère les candidats de plan, leur génération progressive et leur
publication. Il ne génère pas les fiches de révision.
"""

from __future__ import annotations

from datetime import datetime
import re
import shutil
import unicodedata
from pathlib import Path

from src.config import COURSE_PDF_DIR, PLAN_DIR, STUDY_MODEL
from src.courses.planner import (
    _generic_title,
    _id,
    extract_document,
    generate_overviews,
    initial_plan,
    preview_snapshot,
    restore_preview,
)
from src.storage.repository import read_json, write_json_atomic


def normalize_name(value: str) -> str:
    """Normalise un nom pour permettre une recherche tolérante."""
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", value)


def find_course_pdf(query: str) -> Path:
    """Retourne l'unique PDF dont le nom correspond à ``query``."""
    matches = [
        path
        for path in COURSE_PDF_DIR.glob("*.pdf")
        if normalize_name(query) in normalize_name(path.stem)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Sélection ambiguë : {len(matches)} PDF correspondent à {query!r}. "
            "Précise davantage le nom du cours."
        )
    return matches[0]


def plan_paths(pdf: Path) -> tuple[Path, Path]:
    """Retourne ``(plan publié, candidat)`` pour un PDF."""
    active = PLAN_DIR / f"{pdf.stem}.json"
    candidate = PLAN_DIR / f"{pdf.stem}.candidate.json"
    return active, candidate


def load_plan_file(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Fichier absent : {path}")
    return read_json(path)


def save_plan_file(path: Path, value: dict) -> None:
    """Écrit uniquement dans le dossier dédié aux plans."""
    if path.parent != PLAN_DIR:
        raise ValueError("Écriture hors du dossier des plans refusée.")
    write_json_atomic(path, value)


def validate_candidate(candidate: dict, pdf: Path, document: dict | None = None) -> dict:
    """Valide le hash, la couverture des pages et la structure d'un candidat."""
    if candidate.get("consolidation", {}).get("version") != 1:
        raise ValueError("Candidat de plan absent ou non identifié.")
    if candidate.get("mode") != "thematic_ai_draft":
        raise ValueError("Mode de plan incompatible.")
    if document is None:
        document = extract_document(pdf)

    plan = restore_preview(candidate, document)
    for index, part in enumerate(plan["parts"], 1):
        start, end = part["page_start"], part["page_end"]
        if (
            part.get("number") != str(index)
            or part.get("source_pages") != list(range(start, end + 1))
            or part.get("title_status") != "draft"
            or not part.get("title", "").strip()
        ):
            raise ValueError(f"Partie {index} : numéro, pages ou titre incomplet.")
        if part["overview"].get("status") not in {
            "draft",
            "pending",
            "error",
            "not_applicable",
        }:
            raise ValueError(f"Partie {index} : statut de vue d'ensemble invalide.")
    if not plan["parts"]:
        raise ValueError("Aucune partie dans le candidat.")
    return plan


def overview_summary(candidate: dict) -> dict[str, int]:
    states = [part["overview"]["status"] for part in candidate["parts"]]
    return {
        state: states.count(state)
        for state in ("draft", "pending", "error", "not_applicable")
    }


def build_candidate(pdf: Path, document: dict | None = None) -> dict:
    """Construit un plan candidat validé sans écrire sur disque.

    Cette fonction porte la logique métier réutilisable par la CLI et par
    l'import web. Les écritures restent à la charge de l'appelant.
    """
    if document is None:
        document = extract_document(pdf)

    base = initial_plan(document)
    page_count = document["page_count"]

    if base["mode"] == "numbered":
        anchors = {1}
        labels: dict[int, str] = {}
        for part in base["parts"]:
            page = part["page_start"]
            if 1 <= page <= page_count:
                anchors.add(page)
                labels.setdefault(page, part["title"])

        cuts = sorted(anchors)
        ranges = [
            (start, cuts[index + 1] - 1 if index + 1 < len(cuts) else page_count)
            for index, start in enumerate(cuts)
        ]

        # Une sous-section d'une seule page peut être rattachée au bloc précédent.
        # Aucune taille maximale arbitraire n'est imposée à une partie.
        merged: list[tuple[int, int]] = []
        for start, end in ranges:
            if merged and end - start + 1 < 2:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))
        ranges = merged

        def title_for(start: int, end: int, index: int) -> str:
            nearby = next(
                (labels[page] for page in sorted(labels) if start <= page <= end),
                None,
            )
            return (
                nearby
                or _generic_title(document["pages"][start - 1 : end], index)
            )[:90]

    else:
        from src.courses.plan_boundaries import contextual_boundaries, _partition

        ranges = _partition(
            document["pages"],
            contextual_boundaries(document["pages"]),
        )

        def title_for(start: int, end: int, index: int) -> str:
            return _generic_title(document["pages"][start - 1 : end], index)[:90]

    parts = []
    for index, (start, end) in enumerate(ranges, start=1):
        parts.append(
            {
                "id": _id(document["file_hash"], f"pages:{start}:{end}"),
                "number": str(index),
                "title": title_for(start, end, index),
                "page_start": start,
                "page_end": end,
                "title_origin": "pdf_proposal",
                "title_status": "draft",
                "overview": {"status": "pending"},
                "source_pages": list(range(start, end + 1)),
            }
        )

    candidate = {
        "plan_version": 1,
        "filename": pdf.name,
        "file_hash": document["file_hash"],
        "page_count": page_count,
        "mode": "thematic_ai_draft",
        "status": "draft",
        "model": STUDY_MODEL,
        "parts": parts,
        "warnings": [
            "Découpage indicatif : relire les frontières et les titres avant publication."
        ],
        "page_diagnostics": [
            {"page": page["page"], "warnings": page["warnings"]}
            for page in document["pages"]
            if page["warnings"]
        ],
        "consolidation": {
            "version": 1,
            "origin": "new_pdf_proposal",
            "review_required": True,
        },
    }

    validate_candidate(candidate, pdf, document)
    return candidate


def prepare_candidate(pdf: Path, candidate_path: Path) -> None:
    """Crée un candidat initial sans modifier le plan publié ni les fiches."""
    if candidate_path.exists():
        raise ValueError("Un candidat existe déjà pour ce PDF.")

    candidate = build_candidate(pdf)
    save_plan_file(candidate_path, candidate)
    print(f"Candidat créé : {candidate_path} | {len(candidate['parts'])} parties.")
    print("Vérifie les frontières et les titres avant de générer les vues d'ensemble.")

def show_plan_status(
    pdf: Path,
    active_path: Path,
    candidate_path: Path,
    candidate: dict,
) -> None:
    """Affiche l'état d'un candidat sans écrire sur disque."""
    validate_candidate(candidate, pdf)
    counts = overview_summary(candidate)
    print(
        f"PDF : {pdf.name} | {candidate['page_count']} pages | "
        f"{len(candidate['parts'])} parties"
    )
    print(f"Candidat : {candidate_path.name} | vues d'ensemble : {counts}")
    for part in candidate["parts"]:
        print(
            f"  {part['number']:>2}. p.{part['page_start']}-{part['page_end']} "
            f"| {part['title']} | {part['overview']['status']}"
        )
    if active_path.is_file():
        current = load_plan_file(active_path)
        status = "identique au candidat" if current == candidate else "différent du candidat"
        print(f"Plan publié : {active_path.name} | {status}")
    else:
        print("Plan publié : absent")


def generate_candidate_overviews(
    pdf: Path,
    candidate_path: Path,
    candidate: dict,
    model: str,
    limit: int | None,
    force_parts: set[str] | None = None,
) -> None:
    """Génère ou reprend les vues d'ensemble d'un candidat."""
    document = extract_document(pdf)
    plan = validate_candidate(candidate, pdf, document)

    if model != candidate.get("model", model) and overview_summary(candidate)["draft"]:
        raise ValueError(
            "Changer de modèle au milieu d'une génération est refusé ; "
            "garde le modèle enregistré dans le candidat."
        )

    plan["model"] = model
    force_parts = force_parts or set()
    existing_numbers = {str(part["number"]) for part in plan["parts"]}
    unknown = force_parts - existing_numbers
    if unknown:
        raise ValueError(
            "Parties inexistantes demandées : " + ", ".join(sorted(unknown))
        )

    def checkpoint(current: dict, part: dict) -> None:
        save_plan_file(candidate_path, preview_snapshot(current))
        print(
            f"  Partie {part['number']}/{len(current['parts'])} : "
            f"{part['overview']['status']}",
            flush=True,
        )
        if part["overview"]["status"] == "error":
            print(
                "    Cause : " + part["overview"].get("message", "non précisée"),
                flush=True,
            )

    generate_overviews(
        plan,
        document,
        model,
        progress_callback=checkpoint,
        max_parts=limit,
        force_parts=force_parts,
    )
    save_plan_file(candidate_path, preview_snapshot(plan))

    counts = overview_summary(plan)
    print(f"Candidat sauvegardé. Vues d'ensemble : {counts}.")
    if counts["pending"] or counts["error"]:
        print("Relance la même commande pour reprendre uniquement les parties inachevées.")
    else:
        print("Génération achevée : le candidat peut être contrôlé puis publié.")


def publish_candidate(
    pdf: Path,
    active_path: Path,
    candidate_path: Path,
    candidate: dict,
) -> None:
    """Publie un candidat complet après sauvegarde du plan actif éventuel."""
    validate_candidate(candidate, pdf)
    states = overview_summary(candidate)
    if states["pending"] or states["error"]:
        raise ValueError(
            "Publication refusée : vues d'ensemble encore pending/error."
        )

    if active_path.is_file():
        previous = load_plan_file(active_path)
        if (
            previous.get("filename") != pdf.name
            or previous.get("file_hash") != candidate["file_hash"]
        ):
            raise ValueError(
                "Plan publié incompatible : pas d'écrasement automatique."
            )
        if previous == candidate:
            print("Déjà publié : plan actif identique, aucun fichier modifié.")
            return

        baseline = candidate.get("review", {}).get("base_fingerprint")
        if baseline:
            from src.courses.plan_review import preview_fingerprint

            if preview_fingerprint(previous) != baseline:
                raise ValueError(
                    "Le plan actif a changé depuis la revue : publication refusée."
                )

        backup_folder = PLAN_DIR / "_backups"
        backup_folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = backup_folder / f"{pdf.stem}.before_plan_publish.{stamp}.json"
        shutil.copy2(active_path, backup)
        print(f"Ancien plan sauvegardé : {backup}")

    save_plan_file(active_path, candidate)
    print(f"Plan publié : {active_path}")
