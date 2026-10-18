"""Commandes développeur de StudyPilot.

Les commandes de maintenance sont regroupées ici pour éviter les scripts
temporaires à la racine du projet.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from src.ai.client import AITransientError, AIUsageLimitError
from src.console import configure_console

from src.config import AI_PROVIDER, COURSE_DATA_DIR, COURSE_PDF_DIR, PLAN_DIR, PROJECT_ROOT, STUDY_MODEL
from src.courses.plan_manager import (
    find_course_pdf,
    generate_candidate_overviews,
    load_plan_file,
    plan_paths,
    prepare_candidate,
    publish_candidate,
    show_plan_status,
)

from src.courses.service import canonical_storage_status, find_course
from src.courses.inventory import build_inventory, inventory_summary
from src.courses.cards import build_cards, cards_summary, preview_card


def doctor() -> int:
    checks = {
        "Flask": importlib.util.find_spec("flask") is not None,
        "PyMuPDF": importlib.util.find_spec("pymupdf") is not None,
        "Pydantic": importlib.util.find_spec("pydantic") is not None,
        "Ollama (package Python)": importlib.util.find_spec("ollama") is not None,
    }
    print(f"StudyPilot : {PROJECT_ROOT}")
    print(f"Modèle principal : {STUDY_MODEL}")
    print(f"Fournisseur : {AI_PROVIDER}")
    print(f"PDF : {COURSE_PDF_DIR}")
    print(f"Plans : {PLAN_DIR}")
    print(f"Stockage par cours : {COURSE_DATA_DIR}\n")
    for name, available in checks.items():
        print(f"[{'OK' if available else 'MANQUANT'}] {name}")
    required = [checks["Flask"], checks["PyMuPDF"], checks["Pydantic"]]
    if AI_PROVIDER == 'gemma':
        import os
        try:
            sdk_available = importlib.util.find_spec('google.genai') is not None
        except (ModuleNotFoundError, ValueError):
            sdk_available = False
        print(f"[{'OK' if sdk_available else 'MANQUANT'}] Google GenAI SDK")
        required.append(sdk_available)
        available = bool(os.environ.get('GEMINI_API_KEY', '').strip())
        print(f"[{'OK' if available else 'MANQUANT'}] GEMINI_API_KEY (valeur masquée)")
        required.append(available)
    return 0 if all(required) else 1


def run_tests(full: bool = False) -> int:
    return subprocess.call(
        [sys.executable, "-X", "utf8", "tests/run.py"] + (["--full"] if full else []),
        cwd=Path(PROJECT_ROOT),
    )


def _parse_part_numbers(raw: str | None) -> set[str]:
    if raw is None:
        return set()
    values = [value.strip() for value in raw.split(",") if value.strip()]
    if not values or not all(value.isdigit() for value in values):
        raise ValueError(
            '--redo-parts attend des numéros séparés par des virgules, exemple : "2,5,7".'
        )
    return set(values)


def run_plan_command(args: argparse.Namespace) -> int:
    pdf = find_course_pdf(args.course)
    active_path, candidate_path = plan_paths(pdf)

    if args.plan_command == "prepare":
        prepare_candidate(pdf, candidate_path)
        return 0

    candidate = load_plan_file(candidate_path)

    if args.plan_command == "status":
        show_plan_status(pdf, active_path, candidate_path, candidate)
        return 0

    if args.plan_command == "overviews":
        if args.limit is not None and args.limit < 1:
            raise ValueError("--limit attend un entier >= 1.")
        force_parts = _parse_part_numbers(args.redo_parts)
        generate_candidate_overviews(
            pdf,
            candidate_path,
            candidate,
            args.model or STUDY_MODEL,
            args.limit,
            force_parts,
        )
        return 0

    if args.plan_command == "publish":
        publish_candidate(pdf, active_path, candidate_path, candidate)
        return 0

    raise ValueError("Commande de plan inconnue.")



def run_storage_command(args: argparse.Namespace) -> int:
    if args.storage_command == "status":
        courses = canonical_storage_status()
        if not courses:
            print("Aucun cours dans le stockage canonique.")
            return 0
        for course in courses:
            states = [
                "plan" if course["has_plan"] else "sans plan",
                "inventaire" if course["has_inventory"] else "sans inventaire",
                "fiches" if course["has_cards"] else "sans fiches",
            ]
            print(f"{course['course_id']} | {course['title']} | " + " | ".join(states))
        return 0

    raise ValueError("Commande de stockage inconnue.")




def run_inventory_command(args: argparse.Namespace) -> int:
    course = find_course(args.course)
    course_id = course["course_id"]

    if args.inventory_command == "repair-evidence":
        from src.courses.inventory import repair_inventory_evidence
        result, backup, changed = repair_inventory_evidence(course_id)
        print(f"Preuves réparées ou diagnostiquées : {changed} notions.")
        print(f"{len(result.concepts)} notions conservées | {inventory_summary(result)['insufficient_concepts']} preuve(s) insuffisante(s) | {inventory_summary(result)['ignored_concepts']} mention(s) écartée(s).")
        if backup:
            print(f"Inventaire précédent sauvegardé : {backup}")
        return 0

    if args.inventory_command == "list":
        from pydantic import ValidationError

        from src.models.concept import ConceptInventory
        from src.storage.course_repository import CourseRepository
        from src.storage.repository import StorageError

        try:
            inventory = ConceptInventory.model_validate(
                CourseRepository().load_inventory(course_id)
            )
        except (StorageError, ValidationError):
            print("Inventaire absent ou invalide.")
            return 1

        if not inventory.concepts:
            print("Aucune notion dans l'inventaire.")
            return 0

        print(f"{course['title']} | {len(inventory.concepts)} notions")

        requested_index = getattr(args, "index", None)
        requested_title = getattr(args, "title", None)
        if requested_index is not None and not 1 <= requested_index <= len(inventory.concepts):
            raise ValueError(f"--index doit être compris entre 1 et {len(inventory.concepts)}.")
        for index, concept in enumerate(inventory.concepts, start=1):
            if getattr(args, "issues_only", False) and not concept.evidence_issue:
                continue
            if requested_index is not None and requested_index != index:
                continue
            if requested_title is not None and requested_title.casefold() not in concept.title.casefold():
                continue
            pages = ", ".join(str(page) for page in concept.source_pages)
            print(
                f"{index:02d}. {concept.title} "
                f"[{concept.type}] | p.{pages}"
            )

            if concept.relevance == "mention_only":
                print(f"    MENTION ÉCARTÉE : {concept.relevance_reason}")
            elif concept.evidence_issue:
                print(f"    PREUVE INSUFFISANTE : {concept.evidence_issue}")

            if args.evidence:
                for item in concept.evidence:
                    print(
                        f"    p.{item.page}: "
                        f"{item.excerpt}"
                    )

        return 0

    if args.inventory_command == "build":
        def progress(done: int, total: int, part_number: str, state: str) -> None:
            label = f"partie {part_number}" if part_number else "cours"
            print(f"[{done}/{total}] {label} : {state}")

        inventory = build_inventory(
            course_id,
            model=args.model or STUDY_MODEL,
            force=args.force,
            redo_parts=_parse_part_numbers(getattr(args, "redo_parts", None)) or None,
            progress_callback=progress,
        )
        summary = inventory_summary(inventory)
        print(
            f"Inventaire : {summary['concepts']} notions | "
            f"{summary['complete_parts']} parties complètes | "
            f"{summary['error_parts']} erreur(s)."
            f" {summary['insufficient_concepts']} preuve(s) insuffisante(s)."
        )
        return 0 if summary["error_parts"] == 0 else 2

    if args.inventory_command == "status":
        from src.models.concept import ConceptInventory
        from src.storage.course_repository import CourseRepository
        from pydantic import ValidationError
        from src.storage.repository import StorageError

        try:
            inventory = ConceptInventory.model_validate(CourseRepository().load_inventory(course_id))
        except (StorageError, ValidationError):
            print("Inventaire absent ou invalide.")
            return 1
        summary = inventory_summary(inventory)
        print(
            f"{course['title']} | {summary['concepts']} notions | "
            f"{summary['complete_parts']}/{len(course_service_plan_parts(course_id))} parties complètes | "
            f"{summary['error_parts']} partie(s) en échec"
            f" | {summary['insufficient_concepts']} preuve(s) insuffisante(s)"
        )
        for part in inventory.parts:
            extra = f" (+{part.concepts_added_by_audit} par audit)" if part.concepts_added_by_audit else ""
            print(f"  Partie {part.part_number}: {part.status} | {part.concepts_found} notions{extra}")
            if part.message:
                print(f"    {part.message}")
        return 0

    raise ValueError("Commande d'inventaire inconnue.")

def run_cards_command(args: argparse.Namespace) -> int:
    course = find_course(args.course)
    course_id = course["course_id"]

    if args.cards_command == "preview":
        concept, card = preview_card(
            course_id,
            args.index,
            concept_title=getattr(args, "title", None),
            model=args.model or STUDY_MODEL,
        )

        print(f"Notion : {concept.title}")
        print(f"Type : {concept.type}")
        print(
            "Pages sources : "
            + ", ".join(str(page) for page in concept.source_pages)
        )
        print()
        print(card.model_dump_json(indent=2))
        return 0

    if args.cards_command == "build":
        def progress(done: int, total: int, part_number: str, state: str) -> None:
            print(f"[{done}/{total}] partie {part_number} : {state}")

        collection = build_cards(
            course_id,
            model=args.model or STUDY_MODEL,
            force=args.force,
            progress_callback=progress,
        )

        summary = cards_summary(collection)

        print(
            f"Fiches : {summary['cards']} | "
            f"{summary['complete_parts']} parties complètes | "
            f"{summary['partial_parts']} partielles | "
            f"{summary['insufficient_sources']} source(s) insuffisante(s) | "
            f"{summary['ignored_concepts']} mention(s) écartée(s) | "
            f"{summary.get('review_issues', 0)} revue(s) à reprendre | "
            f"{summary['error_parts']} erreur(s)."
        )

        return 2 if any(summary.get(k, 0) for k in ('error_parts', 'partial_parts', 'blocked_concepts', 'failed_concepts', 'review_issues')) else 0

    if args.cards_command == "status":
        from pydantic import ValidationError

        from src.models.card import CardCollection
        from src.storage.course_repository import CourseRepository
        from src.storage.repository import StorageError, read_json

        try:
            preparation = read_json(CourseRepository().paths(course_id).root / 'pedagogy.json')
        except StorageError:
            preparation = {}
        try:
            collection = CardCollection.model_validate(
                CourseRepository().load_cards(course_id)
            )
        except (StorageError, ValidationError):
            print("Fiches absentes ou invalides.")
            return 1

        from src.courses.card_presentation import publication_view
        collection = publication_view(collection)
        preparation_pending = bool(preparation) and (
            preparation.get('fingerprint') != collection.quality_hash
            or preparation.get('stage', 'prepared') != 'prepared')
        if preparation_pending:
            print("PRÉPARATION NON PUBLIÉE : les statistiques ci-dessous décrivent la dernière génération enregistrée.")
            print(f"  Lecture : {len(preparation.get('chunks', {}))} passages vérifiés ; "
                  f"pertinence : {len(preparation.get('decisions', {}))} décisions sauvegardées.")
            for issue in preparation.get('issues', []):
                location = issue.get('title') or issue.get('concept_id') or f"p.{issue.get('page', '?')}"
                print(f"  DIAGNOSTIC DE LA PRÉPARATION — {location} : {issue['reason']}")
            print("DERNIÈRE GÉNÉRATION ENREGISTRÉE (les diagnostics suivants peuvent être anciens) :")
        summary = cards_summary(collection)

        print(
            f"{course['title']} | "
            f"{summary['cards']} fiches | "
            f"{summary['complete_parts']}/{summary['parts']} parties complètes | "
            f"{summary['partial_parts']} partielles | "
            f"{summary['insufficient_sources']} source(s) insuffisante(s) | "
            f"{summary['ignored_concepts']} mention(s) écartée(s) | "
            f"{summary.get('review_issues', 0)} revue(s) à reprendre | "
            f"{summary['error_parts']} partie(s) en échec"
        )

        for part in collection.parts:
            print(
                f"  Partie {part.part_number}: "
                f"{part.status} | "
                f"{part.cards_generated} fiches"
            )

            if part.message:
                print(f"    {part.message}")

        for item in collection.blocked:
            pages = ", ".join(map(str, item.source_pages))
            print(f"  SOURCE INSUFFISANTE : {item.title} | p.{pages}")
            print(f"    {item.reason}")
        for item in collection.ignored:
            pages = ", ".join(map(str, item.source_pages))
            print(f"  MENTION ÉCARTÉE : {item.title} | p.{pages}")
            print(f"    {item.reason}")
        for item in collection.failures:
            print(f"  {item.status.upper()} — À REPRENDRE : {item.title} | p.{item.source_pages}")
            print(f"    {item.reason}")
        if collection.unreviewed_cards:
            print(f"  {len(collection.unreviewed_cards)} ancienne(s) fiche(s) sauvegardée(s), en attente de validation.")
        if collection.archived_cards:
            print(f"  {len(collection.archived_cards)} ancienne(s) fiche(s) conservée(s) en archive après regroupement ou exclusion validée.")
        for issue in collection.review_issues:
            location = f"p.{issue['page']}" if issue.get('page') is not None else issue.get('title', 'cours')
            chunk = f" [{issue['chunk_id']}]" if issue.get('chunk_id') else ''
            print(f"  REVUE PÉDAGOGIQUE [{issue.get('status', 'review_pending')}] — {location}{chunk} : {issue['reason']}")
        for relation in collection.relations:
            print(f"  REGROUPEMENT : {relation['title']} → {relation['target_id']} ({relation['reason']})")
        return 2 if preparation_pending or any(summary.get(k, 0) for k in ('error_parts', 'partial_parts', 'blocked_concepts', 'failed_concepts', 'review_issues')) else 0

    raise ValueError("Commande de fiches inconnue.")

def course_service_plan_parts(course_id: str) -> list[dict]:
    from src.courses.service import load_course, load_course_plan
    course = load_course(course_id)
    plan = load_course_plan(course)
    return list(plan.get("parts", [])) if plan else []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Outils développeur StudyPilot")
    commands = parser.add_subparsers(dest="command", required=True)
    process = commands.add_parser("process", help="Construit ou reprend inventaire, preuves et fiches")
    process_target = process.add_mutually_exclusive_group(required=True)
    process_target.add_argument("--course")
    process_target.add_argument("--all", action="store_true", help="Reprend tous les cours enregistrés")
    process.add_argument("--model", default=None)

    commands.add_parser("doctor", help="Vérifie l'environnement local")
    tests = commands.add_parser("test", help="Lance les tests courants sans réseau")
    tests.add_argument('--full', action='store_true', help='Ajouter les régressions historiques et les PDF locaux')
    refresh = commands.add_parser('refresh-overviews', help='Met à niveau les aperçus sans reconstruire les fiches')
    refresh.add_argument('--course', required=True)

    plan = commands.add_parser("plan", help="Prépare, inspecte et publie les plans de cours")
    plan_commands = plan.add_subparsers(dest="plan_command", required=True)

    for name, help_text in (
        ("prepare", "Crée un candidat de plan pour un PDF inédit"),
        ("status", "Inspecte un candidat sans écrire"),
        ("publish", "Publie un candidat complet avec sauvegarde du plan précédent"),
    ):
        command = plan_commands.add_parser(name, help=help_text)
        command.add_argument("--course", required=True, help="Fragment unique du nom du PDF")

    overviews = plan_commands.add_parser(
        "overviews", help="Génère ou reprend les vues d'ensemble d'un candidat"
    )
    overviews.add_argument("--course", required=True, help="Fragment unique du nom du PDF")
    overviews.add_argument("--model", default=None, help="Modèle Ollama à utiliser")
    overviews.add_argument("--limit", type=int, default=None, help="Limite de parties pour diagnostic")
    overviews.add_argument(
        "--redo-parts",
        default=None,
        help='Régénère explicitement certaines parties, exemple : "2,5,7"',
    )

    storage = commands.add_parser("storage", help="Inspecte le stockage des cours")
    storage_commands = storage.add_subparsers(dest="storage_command", required=True)
    storage_commands.add_parser(
        "status", help="Affiche l'état du stockage par cours"
    )

    inventory = commands.add_parser("inventory", help="Construit et inspecte l'inventaire des notions")
    inventory_commands = inventory.add_subparsers(dest="inventory_command", required=True)

    inventory_repair = inventory_commands.add_parser("repair-evidence", help="Répare et diagnostique les preuves existantes sans appel IA")
    inventory_repair.add_argument("--course", required=True, help="Identifiant, titre ou fragment unique du cours")

    inventory_build = inventory_commands.add_parser("build", help="Construit ou reprend l'inventaire d'un cours")
    inventory_build.add_argument("--course", required=True, help="Identifiant, titre ou fragment unique du cours")
    inventory_build.add_argument("--model", default=None, help="Modèle Ollama à utiliser")
    inventory_build.add_argument("--force", action="store_true", help="Reconstruit toutes les parties")
    inventory_build.add_argument("--redo-parts", default=None, help="Reconstruit uniquement les parties indiquées, exemple : 1,3")

    inventory_status = inventory_commands.add_parser("status", help="Affiche l'état de l'inventaire d'un cours")
    inventory_status.add_argument("--course", required=True, help="Identifiant, titre ou fragment unique du cours")

    inventory_list = inventory_commands.add_parser(
        "list",
        help="Liste les notions de l'inventaire avec leur index",
    )
    inventory_list.add_argument(
        "--course",
        required=True,
        help="Identifiant, titre ou fragment unique du cours",
    )
    inventory_list.add_argument(
        "--evidence",
        action="store_true",
        help="Affiche aussi les preuves exactes du PDF",
    )
    inventory_choice = inventory_list.add_mutually_exclusive_group()
    inventory_choice.add_argument("--index", type=int, default=None, help="Affiche uniquement la notion indiquée")
    inventory_choice.add_argument("--title", default=None, help="Filtre les notions par fragment de titre")
    inventory_list.add_argument("--issues-only", action="store_true", help="Affiche uniquement les preuves signalées comme insuffisantes")

    cards = commands.add_parser(
        "cards",
        help="Construit et inspecte les fiches pédagogiques",
    )

    cards_commands = cards.add_subparsers(
        dest="cards_command",
        required=True,
    )

    cards_build = cards_commands.add_parser(
        "build",
        help="Construit ou reprend les fiches d'un cours",
    )
    cards_build.add_argument(
        "--course",
        required=True,
        help="Identifiant, titre ou fragment unique du cours",
    )
    cards_build.add_argument(
        "--model",
        default=None,
        help="Modèle Ollama à utiliser",
    )
    cards_build.add_argument(
        "--force",
        action="store_true",
        help="Reconstruit toutes les parties",
    )

    cards_status = cards_commands.add_parser(
        "status",
        help="Affiche l'état des fiches d'un cours",
    )
    cards_status.add_argument(
        "--course",
        required=True,
        help="Identifiant, titre ou fragment unique du cours",
    )

    cards_preview = cards_commands.add_parser(
        "preview",
        help="Génère une seule fiche sans la sauvegarder",
    )
    cards_preview.add_argument(
        "--course",
        required=True,
        help="Identifiant, titre ou fragment unique du cours",
    )
    preview_choice = cards_preview.add_mutually_exclusive_group(required=True)
    preview_choice.add_argument(
        "--index",
        type=int,
        help="Index 1-based affiché par 'inventory list'",
    )
    preview_choice.add_argument("--title", default=None, help="Titre exact ou fragment unique de la notion")
    cards_preview.add_argument(
        "--model",
        default=None,
        help="Modèle Ollama à utiliser",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    configure_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "process":
            from src.courses.pipeline import process_course
            from src.courses.service import list_courses
            courses = list_courses() if args.all else [find_course(args.course)]
            code = 0
            for course in courses:
                print("Cours : " + course.get('title', course['course_id']))
                try:
                    result = process_course(course["course_id"], model=args.model or STUDY_MODEL,
                        progress_callback=lambda done, total, part, state: print(f"[{done}/{total}] partie {part} : {state}"))
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                    if result["status"] != "ready":
                        code = code or 2
                except AITransientError as error:
                    print(f"PANNE TEMPORAIRE : {error}")
                    code = 4
                except AIUsageLimitError as error:
                    print(f"ARRÊT IA : {error}")
                    return 3
                except Exception as error:
                    print(f"Reprise nécessaire : {type(error).__name__}: {error}")
                    code = code or 2
            return code
        if args.command == "doctor":
            return doctor()
        if args.command == "test":
            return run_tests(args.full)
        if args.command == 'refresh-overviews':
            from src.courses.service import refresh_overviews
            result = refresh_overviews(find_course(args.course)['course_id'],
                progress_callback=lambda part: print('Aperçu ' + part['number'] + ' enregistré.', flush=True))
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result['status'] == 'ready' else 2
        if args.command == "plan":
            return run_plan_command(args)
        if args.command == "storage":
            return run_storage_command(args)
        if args.command == "inventory":
            return run_inventory_command(args)
        if args.command == "cards":
            return run_cards_command(args)

    except AITransientError as error:
        print(f"PANNE TEMPORAIRE : {error}", file=sys.stderr)
        return 4
    except AIUsageLimitError as error:
        print(f"ARRÊT IA : {error}", file=sys.stderr)
        return 3
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"ERREUR : {type(error).__name__}: {error}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
