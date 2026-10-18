"""Validation des PDF et file d'import de StudyPilot.

Chaque nouveau PDF passe par le service de cours et le planner moderne. Les
états de la file sont conservés sur disque. Un traitement interrompu peut être
repris explicitement après redémarrage, sans perdre les checkpoints du cours.
"""

from concurrent.futures import ThreadPoolExecutor
import logging
import os
from pathlib import Path
import re
import tempfile
import threading
import unicodedata
import uuid
from datetime import datetime, timezone
import hashlib

from src.config import DATA_DIR, COURSE_PDF_DIR, MAX_PDF_BYTES, MAX_PDF_PAGES, MAX_PENDING_IMPORTS
from src.storage.repository import read_json, write_json_atomic, StorageError
from src.ai.client import AIUsageLimitError

MAX_PAGES = MAX_PDF_PAGES
MAX_PENDING = MAX_PENDING_IMPORTS
UPLOAD_FOLDER = COURSE_PDF_DIR

_LOGGER = logging.getLogger(__name__)
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="studypilot-import")
_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}
JOB_DIR = DATA_DIR / 'imports'


def _persist(job_id):
    _JOBS[job_id]['updated_at'] = datetime.now(timezone.utc).isoformat()
    write_json_atomic(JOB_DIR / (job_id + '.json'), _JOBS[job_id])


def restore_jobs():
    for path in JOB_DIR.glob('*.json'):
        if not re.fullmatch(r'[0-9a-f]{32}', path.stem):
            continue
        try:
            job = read_json(path)
            if job.get('status') not in {'queued', 'processing', 'interrupted', 'partial', 'error', 'ready'}:
                continue
            # Les chemins ne sont jamais reçus depuis le navigateur et doivent
            # rester dans le répertoire des PDF, y compris lors d'une reprise.
            if Path(job.get('pdf_path', '')).resolve().parent != UPLOAD_FOLDER.resolve():
                continue
            _JOBS[path.stem] = job
            if job['status'] in {'queued', 'processing'}:
                _set_job(path.stem, status='interrupted', error='Le serveur a été arrêté. Reprends l’analyse pour continuer.')
        except (StorageError, OSError, ValueError):
            _LOGGER.warning('Suivi d’import illisible : %s', path.name)


class UploadError(Exception):
    """PDF refusé : message exploitable dans l'interface."""


def _safe_stem(original_name: str) -> str:
    filename = str(original_name or "").replace("\\", "/").split("/")[-1]
    if not filename.lower().endswith(".pdf"):
        raise UploadError("Sélectionne un fichier .pdf.")
    stem = Path(filename).stem.strip()
    if not stem or stem in (".", ".."):
        raise UploadError("Le nom du PDF est invalide.")
    normalized = unicodedata.normalize("NFKD", stem)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", ascii_name).strip("-_ .")[:75]
    return safe or "cours"


def save_validated_pdf(file_stream, original_name: str) -> tuple[Path, str, int]:
    """Valide un PDF texte ou scanné ; vérifie l'OCR si aucun texte n'est natif."""
    stem = _safe_stem(original_name)
    title = Path(str(original_name).replace("\\", "/").split("/")[-1]).stem.strip()[:120]
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=UPLOAD_FOLDER, prefix=".import-", suffix=".tmp", delete=False
        ) as temporary:
            temp_path = Path(temporary.name)
            size = 0
            while True:
                chunk = file_stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_PDF_BYTES:
                    raise UploadError("Le PDF dépasse la limite de 20 Mo.")
                temporary.write(chunk)

        if size < 5:
            raise UploadError("Le fichier PDF est vide ou invalide.")
        with temp_path.open("rb") as check:
            if check.read(5) != b"%PDF-":
                raise UploadError("Ce fichier ne semble pas être un PDF valide.")

        try:
            import pymupdf

            with pymupdf.open(str(temp_path)) as document:
                if document.needs_pass:
                    raise UploadError("Les PDF protégés par mot de passe ne sont pas pris en charge.")
                page_count = document.page_count
                if not 1 <= page_count <= MAX_PAGES:
                    raise UploadError(f"Le PDF doit contenir entre 1 et {MAX_PAGES} pages.")
                if not any(page.get_text("text").strip() for page in document):
                    from src.pdf.ocr import extract_page_sources
                    try:
                        readable = any(extract_page_sources(page)["ocr_text"].strip() for page in document)
                    except Exception as error:
                        raise UploadError(f"Lecture OCR impossible : {error}") from error
                    if not readable:
                        raise UploadError("Aucun texte exploitable après OCR. Vérifie la lisibilité du PDF.")
        except UploadError:
            raise
        except Exception as error:
            raise UploadError("Impossible de lire ce PDF. Vérifie qu'il n'est pas endommagé.") from error

        stored = UPLOAD_FOLDER / f"{stem}-{uuid.uuid4().hex[:10]}.pdf"
        os.replace(temp_path, stored)
        temp_path = None
        return stored, title, page_count
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _set_job(job_id: str, **changes) -> None:
    with _LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(changes)
            _persist(job_id)


def _run_import(job_id: str, job: dict, pdf_path: Path) -> None:
    def progress(completed: int, total: int, part_number: str, state: str) -> None:
        _set_job(
            job_id,
            done=completed,
            total=total,
            current_part=part_number or None,
            current_state=state,
        )

    from src.courses.service import create_course

    from src.courses.service import make_course_id
    _set_job(job_id, course_id=make_course_id(job['title'], hashlib.sha256(pdf_path.read_bytes()).hexdigest()))

    result = create_course(
        pdf_path,
        title=job["title"],
        original_filename=job["original_filename"],
        progress_callback=progress,
    )
    _set_job(
        job_id,
        status=result["status"],
        course_id=result["course_id"],
        done=result["done"],
        total=result["total"],
        incomplete=result["incomplete"],
    )


def _run_job(job_id: str) -> None:
    with _LOCK:
        job = dict(_JOBS[job_id])
        _JOBS[job_id]["status"] = "processing"
        _persist(job_id)

    pdf_path = Path(job["pdf_path"])
    try:
        _run_import(job_id, job, pdf_path)
    except AIUsageLimitError as error:
        _set_job(job_id, status='interrupted', error=str(error)[:900])
    except Exception:
        _LOGGER.exception("Échec du traitement StudyPilot %s", job_id)
        _set_job(
            job_id,
            status="error",
            error=(
                "Le traitement a échoué. Le PDF a été conservé pour éviter toute perte ; "
                "consulte le terminal puis réessaie."
            ),
        )


def enqueue_pdf(file_stream, original_filename: str) -> str:
    """Place un PDF validé dans la file du worker."""
    with _LOCK:
        pending = sum(job["status"] in ("queued", "processing") for job in _JOBS.values())
        if pending >= MAX_PENDING:
            raise UploadError("Trop de cours sont en cours de traitement. Réessaie dans quelques minutes.")

    path, title, pages = save_validated_pdf(file_stream, original_filename)
    job_id = uuid.uuid4().hex
    with _LOCK:
        pending = sum(job["status"] in ("queued", "processing") for job in _JOBS.values())
        if pending >= MAX_PENDING:
            path.unlink(missing_ok=True)
            raise UploadError("La file d'attente est pleine. Réessaie un peu plus tard.")
        _JOBS[job_id] = {
            "status": "queued",
            "title": title,
            "original_filename": str(original_filename).replace("\\", "/").split("/")[-1],
            "pdf_path": str(path),
            "pages": pages,
            "error": None,
            "course_id": None,
            "done": 0,
            "total": 0,
            "current_part": None,
            "current_state": None,
            "incomplete": None,
        }
        _persist(job_id)
    try:
        _EXECUTOR.submit(_run_job, job_id)
    except Exception:
        with _LOCK:
            _JOBS.pop(job_id, None)
            (JOB_DIR / (job_id + '.json')).unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise
    return job_id


def resume_job(job_id: str) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise UploadError('Import introuvable.')
        if job['status'] not in {'interrupted', 'partial', 'error'}:
            raise UploadError('Cet import est terminé ou déjà en cours.')
        if sum(j['status'] in {'queued', 'processing'} for j in _JOBS.values()) >= MAX_PENDING:
            raise UploadError('La file d’attente est pleine.')
        pdf = Path(job['pdf_path']).resolve()
        if pdf.parent != UPLOAD_FOLDER.resolve() or not pdf.is_file():
            raise UploadError('Le PDF de cet import est introuvable.')
        previous = dict(job)
        job.update(status='queued', error=None)
        _persist(job_id)
    try:
        _EXECUTOR.submit(_run_job, job_id)
    except Exception:
        with _LOCK:
            _JOBS[job_id] = previous
            _persist(job_id)
        raise


def job_status(job_id: str) -> dict | None:
    """Copie publique des états ; ne révèle jamais les chemins du disque."""
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        keys = (
            "status", "title", "pages", "error", "course_id", "done", "total",
            "current_part", "current_state", "incomplete",
        )
        return {key: job.get(key) for key in keys}
