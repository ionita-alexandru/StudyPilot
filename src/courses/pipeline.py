"""Traitement commun à l'import et à la reprise d'un cours existant."""
from src.config import STUDY_MODEL
from src.courses.guide_generation import build_guide


def process_course(course_id, *, model=STUDY_MODEL, progress_callback=None):
    return build_guide(course_id, model=model, progress_callback=progress_callback)
