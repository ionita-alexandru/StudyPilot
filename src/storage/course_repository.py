"""Stockage canonique des cours StudyPilot.

Chaque cours possède un espace stable dans ``data/courses/<course_id>/``.
Ce dépôt ne connaît pas Flask ni le pipeline historique : il se contente de
lire et écrire les documents métier du cours de façon sûre.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from src.config import COURSE_DATA_DIR
from src.storage.repository import read_json, write_json_atomic


_COURSE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,119}$")


@dataclass(frozen=True)
class CoursePaths:
    root: Path
    course: Path
    plan: Path
    inventory: Path
    cards: Path


class CourseRepository:
    """Accès aux données canoniques d'un cours."""

    def __init__(self, root: str | Path = COURSE_DATA_DIR):
        self.root = Path(root)

    @staticmethod
    def validate_course_id(course_id: str) -> str:
        value = str(course_id).strip()
        if not _COURSE_ID_RE.fullmatch(value):
            raise ValueError("Identifiant de cours invalide.")
        return value

    def paths(self, course_id: str) -> CoursePaths:
        safe_id = self.validate_course_id(course_id)
        root = self.root / safe_id
        return CoursePaths(
            root=root,
            course=root / "course.json",
            plan=root / "plan.json",
            inventory=root / "inventory.json",
            cards=root / "cards.json",
        )

    def save_course(self, course_id: str, data: dict[str, Any]) -> Path:
        paths = self.paths(course_id)
        return write_json_atomic(paths.course, data)

    def load_course(self, course_id: str) -> dict:
        return read_json(self.paths(course_id).course)

    def save_plan(self, course_id: str, data: dict[str, Any]) -> Path:
        return write_json_atomic(self.paths(course_id).plan, data)

    def load_plan(self, course_id: str) -> dict:
        return read_json(self.paths(course_id).plan)

    def save_inventory(self, course_id: str, data: dict[str, Any]) -> Path:
        return write_json_atomic(self.paths(course_id).inventory, data)

    def load_inventory(self, course_id: str) -> dict:
        return read_json(self.paths(course_id).inventory)

    def save_cards(self, course_id: str, data: dict[str, Any]) -> Path:
        return write_json_atomic(self.paths(course_id).cards, data)

    def load_cards(self, course_id: str) -> dict:
        return read_json(self.paths(course_id).cards)

    def list_course_ids(self) -> list[str]:
        if not self.root.exists():
            return []
        ids: list[str] = []
        for folder in self.root.iterdir():
            if not folder.is_dir() or not (folder / "course.json").is_file():
                continue
            try:
                ids.append(self.validate_course_id(folder.name))
            except ValueError:
                continue
        return sorted(ids)
