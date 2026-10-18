from __future__ import annotations

from typing import Any
from urllib.parse import quote

from src.courses import service as course_service


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")

    raise TypeError(
        f"Objet non sérialisable : {type(value).__name__}"
    )


def revision_course_data(
    course_id: str,
    part_number: str | None = None,
) -> dict:
    """
    Charge les vraies fiches StudyPilot utilisables
    dans une session de révision.

    part_number=None :
        tout le cours

    part_number="2" :
        seulement la partie 2
    """

    course = course_service.load_course(course_id)
    plan = course_service.load_course_plan(course)

    if plan is None:
        raise ValueError(
            "Ce cours ne possède pas de plan."
        )

    parts = list(plan.get("parts") or [])

    if not parts:
        raise ValueError(
            "Ce cours ne contient aucune partie."
        )

    selected_parts: list[dict] = []

    for part in parts:
        number = str(
            part.get("number") or ""
        ).strip()

        if (
            part_number is None
            or number == str(part_number)
        ):
            selected_parts.append(part)


    if part_number is not None and not selected_parts:
        raise ValueError(
            "Partie introuvable."
        )


    cards: list[dict] = []
    seen_cards = set()


    for part in selected_parts:

        part_id = str(
            part.get("id") or ""
        ).strip()

        if not part_id:
            continue


        part_cards = course_service.load_part_cards(
            course,
            part_id,
        )


        for card in part_cards:

            data = _as_dict(card)
            if data.get('card_id') in seen_cards:
                continue
            if part_number is None and data.get('primary_part_id') != part_id:
                continue
            seen_cards.add(data.get('card_id'))

            data["part_number"] = str(
                part.get("number") or ""
            )

            data["part_title"] = str(
                part.get("title") or ""
            )

            cards.append(data)


    if not cards:
        raise ValueError(
            "Aucune fiche validée disponible. Le traitement pédagogique du cours doit être terminé ou repris."
        )


    return {
        "course": {
            "course_id": course["course_id"],
            "title": course["title"],
            "pdf_url": "/pdf/" + quote(course.get("source_filename", "")),
        },

        "parts": [
            {
                "number": str(
                    part.get("number") or ""
                ),
                "title": str(
                    part.get("title") or ""
                ),
            }
            for part in parts
        ],

        "selected_part": part_number,

        "cards": cards,

        "card_count": len(cards),
    }
