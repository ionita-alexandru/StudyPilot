"""Configuration centrale de StudyPilot."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("STUDYPILOT_DATA_DIR", str(PROJECT_ROOT / "data"))).resolve()

COURSE_PDF_DIR = DATA_DIR / "pdfs"
COURSE_DATA_DIR = DATA_DIR / "courses"
PLAN_DIR = DATA_DIR / "plans"

# Modèle unique utilisé par tout StudyPilot :
# plan, inventaire, fiches et chat.
AI_PROVIDER = os.getenv("STUDYPILOT_AI_PROVIDER", "ollama").strip().lower()
STUDY_MODEL = os.getenv(
    "STUDYPILOT_MODEL",
    "gemma-4-31b-it" if AI_PROVIDER == "gemma" else "gemini-3.8-flash" if AI_PROVIDER == "gemini" else "gpt-oss:120b-cloud",
)

# Réglages communs des appels IA.
DEFAULT_TEMPERATURE = 0.1
AI_NUM_CTX = int(
    os.getenv("STUDYPILOT_NUM_CTX", "8192")
)
AI_KEEP_ALIVE = os.getenv(
    "STUDYPILOT_KEEP_ALIVE",
    "10m",
)

# StudyPilot privilégie des réponses directes :
# le raisonnement interne Qwen3 n'est pas utile ici.
AI_THINK = os.getenv(
    "STUDYPILOT_THINK",
    "low",
)

MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_PENDING_IMPORTS = 3
