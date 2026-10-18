"""Lecture et écriture fiables des fichiers JSON StudyPilot."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any


class StorageError(RuntimeError):
    """Erreur de lecture ou d'écriture d'une donnée persistante."""


def _details(error: BaseException) -> str:
    codes = []
    for name in ('winerror', 'errno'):
        code = getattr(error, name, None)
        if code is not None:
            codes.append(f'{name}={code}')
    suffix = f" ({', '.join(codes)})" if codes else ''
    return f'{type(error).__name__}{suffix}: {error}'


def read_json(path: str | Path) -> dict:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError) as error:
        raise StorageError(f"Impossible de lire le JSON : {source} — {_details(error)}") from error
    if not isinstance(data, dict):
        raise StorageError(f"Le JSON doit contenir un objet : {source}")
    return data


def _replace_with_retry(temporary: Path, destination: Path) -> None:
    # Windows : partage/verrouillage et refus d'accès parfois transitoire
    # (lecteur concurrent, indexation, antivirus). Aucun retry illimité.
    delays = (0.05, 0.10, 0.20, 0.40, 0.80)
    for attempt in range(len(delays) + 1):
        try:
            os.replace(temporary, destination)
            return
        except OSError as error:
            if getattr(error, 'winerror', None) not in {5, 32, 33} or attempt == len(delays):
                raise
            time.sleep(delays[attempt])


def write_json_atomic(
    path: str | Path,
    data: dict[str, Any],
    *,
    indent: int = 2,
) -> Path:
    """Chaque écriture possède son temporaire, fermé avant remplacement.

    Un échec laisse la destination précédente intacte. Deux écrivains ne
    partagent jamais leur temporaire ; cela ne remplace pas un verrou de
    traitement à l'échelle d'un cours (la dernière écriture réussie gagne).
    """
    destination = Path(path)
    temporary = None
    failure = None
    stage = 'sérialisation'
    try:
        content = json.dumps(data, ensure_ascii=False, indent=indent) + "\n"
        stage = 'création du dossier'
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage = 'création du fichier temporaire'
        # Même dossier/volume pour conserver l'atomicité de os.replace.
        descriptor, name = tempfile.mkstemp(prefix=destination.name + '.', suffix='.tmp', dir=destination.parent)
        temporary = Path(name)
        stage = 'écriture du fichier temporaire'
        try:
            stream = os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n')
        except BaseException:
            os.close(descriptor)
            raise
        with stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        stage = 'remplacement atomique'
        _replace_with_retry(temporary, destination)
    except (OSError, TypeError, ValueError) as error:
        failure = StorageError(f"Impossible d'écrire le JSON : {destination} — étape : {stage} — {_details(error)}")
        raise failure from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as cleanup_error:
                # Une erreur de nettoyage ne doit pas cacher celle d'origine.
                if failure is not None:
                    failure.args = (f'{failure.args[0]} — temporaire non supprimé : {temporary} — {_details(cleanup_error)}',)
    return destination
