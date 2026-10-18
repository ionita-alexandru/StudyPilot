"""Gemma hébergé : SDK Google, contrat validé par client.chat_json, débit partagé.

Aucune clé dans les fichiers, journaux ou exceptions. Aucun repli de modèle.
"""
from __future__ import annotations

import base64
import io
from contextlib import contextmanager
import json
import hashlib
import os
import random
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import Request

from src.config import DATA_DIR
from src.ai.client import AIUnavailableError, AIUsageLimitError, AIInputTooLargeError, AITransientError

BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/models/'
MODELS = {'gemma-4-31b-it', 'gemma-4-26b-a4b-it'}
# Marge sur les limites observées : 30 RPM / 16 000 TPM.
RPM = 28
TPM = 14400
WINDOW = 61.0
_THREAD_LOCK = threading.Lock()


class GemmaServiceError(AIUnavailableError, AIUsageLimitError):
    """Erreur fournisseur fatale : ne pas la convertir en source insuffisante."""


class GemmaTransientError(GemmaServiceError, AITransientError):
    """Erreur 5xx épuisant les relances, distincte du quota."""


def _send(request, timeout):
    """Adapter le SDK au contrat de transport ; les relances restent partagées."""
    try:
        from google import genai
        from google.genai import types, errors
        import httpx
    except ImportError:
        raise GemmaServiceError('Installer le SDK dans le venv : python -m pip install -U "google-genai>=2.29,<3"') from None
    model, method = request.full_url[len(BASE_URL):].split(':', 1)
    payload = json.loads(request.data)
    options = types.HttpOptions(api_version='v1beta', timeout=timeout * 1000,
        retry_options=types.HttpRetryOptions(attempts=1))
    try:
        with genai.Client(api_key=request.get_header('X-goog-api-key'), http_options=options) as sdk:
            if method == 'countTokens':
                # Le SDK ne prend pas system_instruction dans CountTokensConfig
                # pour l'API Developer. extra_body transmet la requête complète,
                # officiellement acceptée par countTokens, sans la tronquer.
                response = sdk.models.count_tokens(model=model, contents=None,
                    config=types.CountTokensConfig(http_options=types.HttpOptions(extra_body=payload)))
            elif method == 'generateContent':
                contents = []
                for content in payload['contents']:
                    parts = []
                    for part in content['parts']:
                        if 'text' in part:
                            parts.append(types.Part.from_text(text=part['text']))
                        elif 'inlineData' in part:
                            blob = part['inlineData']
                            parts.append(types.Part.from_bytes(data=base64.b64decode(blob['data'], validate=True),
                                mime_type=blob['mimeType']))
                    contents.append(types.Content(role=content['role'], parts=parts))
                config = types.GenerateContentConfig(**payload['generationConfig'],
                    system_instruction=payload.get('systemInstruction'))
                response = sdk.models.generate_content(model=model, contents=contents, config=config)
            else:
                raise GemmaServiceError('Opération SDK non prise en charge.')
            return io.BytesIO(json.dumps(response.model_dump(mode='json', by_alias=True,
                exclude_none=True)).encode('utf-8'))
    except errors.APIError as error:
        # Conserver seulement code/statut : jamais le message fournisseur brut.
        status = getattr(error, 'status', 'UNKNOWN')
        allowed = {'INTERNAL', 'UNAVAILABLE', 'INVALID_ARGUMENT', 'PERMISSION_DENIED',
            'UNAUTHENTICATED', 'RESOURCE_EXHAUSTED', 'NOT_FOUND', 'DEADLINE_EXCEEDED', 'FAILED_PRECONDITION'}
        status = status if isinstance(status, str) and status in allowed else 'UNKNOWN'
        raise HTTPError(request.full_url, error.code, 'Erreur SDK', {},
            io.BytesIO(json.dumps({'error': {'status': status}}).encode())) from None
    except httpx.HTTPError:
        raise URLError('Connexion SDK indisponible') from None
    except (ValueError, ImportError):
        raise GemmaServiceError('Gemma : configuration ou réponse du SDK invalide. '
            'Arrêt technique ; vérifier la version google-genai installée.') from None


def _failure_status(error):
    # Liste positive : aucun message brut (clé ou extraits potentiels).
    try:
        body = json.loads(error.read(16384))
        status = body.get('error', {}).get('status')
    except (ValueError, OSError, AttributeError):
        return 'UNKNOWN'
    return status if isinstance(status, str) and status in {'INTERNAL', 'UNAVAILABLE', 'INVALID_ARGUMENT',
        'PERMISSION_DENIED', 'UNAUTHENTICATED', 'RESOURCE_EXHAUSTED',
        'NOT_FOUND', 'DEADLINE_EXCEEDED', 'FAILED_PRECONDITION'} else 'UNKNOWN'


def _record_failure(model, method, payload, code, status, attempt, tokens):
    path = DATA_DIR / '_ai' / 'gemma_failures.json'
    entry = {'time': time.time(), 'model': model, 'method': method,
        'http_status': code, 'api_status': status, 'attempt': attempt,
        'input_tokens': tokens,
        'input_hash': hashlib.sha256(json.dumps(payload, ensure_ascii=False,
            sort_keys=True).encode('utf-8')).hexdigest()}
    # Localisation sans enregistrer le prompt, les pixels ou la clé.
    for content in payload.get('contents', []):
        if content.get('role') != 'user':
            continue
        for part in content.get('parts', []):
            try:
                value = json.loads(part.get('text', '').split('\nRéponse précédente rejetée :', 1)[0])
            except (ValueError, TypeError):
                continue
            source = value.get('source') if isinstance(value, dict) else None
            if isinstance(source, dict):
                source_id, page = source.get('id'), source.get('page')
                if isinstance(source_id, str) and len(source_id) < 80 and all(c.isalnum() or c in '-_' for c in source_id):
                    entry['source_id'] = source_id
                if isinstance(page, int) and not isinstance(page, bool):
                    entry['source_page'] = page
    try:
        with _locked(path.with_suffix('.lock')):
            entries = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
            if not isinstance(entries, list):
                raise ValueError('diagnostic invalide')
            entries = entries[-99:] + [entry]
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
                json.dump(entries, handle, ensure_ascii=False, indent=2); temporary = Path(handle.name)
            try:
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
    except (ValueError, OSError):
        raise GemmaServiceError('Gemma : erreur fournisseur et diagnostic local impossible à écrire. '
            'Arrêt sans effacement du diagnostic précédent.') from None


def _post(model, method, payload, *, retry_tokens=None):
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    if key and any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise GemmaServiceError('GEMINI_API_KEY contient des espaces ou caractères incompatibles : recopier uniquement la clé depuis AI Studio.')
    if not key:
        raise GemmaServiceError('GEMINI_API_KEY absent : configurer la clé dans ce terminal.')
    request = Request(BASE_URL + model + ':' + method,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'), method='POST',
        headers={'Content-Type': 'application/json', 'x-goog-api-key': key})
    for attempt in range(1, 4):
        from src.ai.workload import request_attempt
        request_attempt(retry_tokens or 0, payload.get('generationConfig', {}).get('maxOutputTokens', 0))
        try:
            with _send(request, timeout=180) as response:
                return json.load(response)
        except HTTPError as error:
            code = error.code
            status = _failure_status(error)
            error.close()
            _record_failure(model, method, payload, code, status, attempt, retry_tokens)
            if code == 429:
                raise AIUsageLimitError('Gemma : HTTP 429, quota ou capacité atteint. '
                    'Passe interrompue sans relance ; checkpoints conservés.') from None
            if code in {500, 502, 503, 504} and attempt < 3:
                delay = 2 ** attempt + random.uniform(0, 1)
                print(f'Gemma : HTTP {code} ({status}), relance {attempt}/2 de {method} '
                    f'après {delay:.1f} s ; même modèle et mêmes sources.', flush=True)
                time.sleep(delay)
                if method == 'generateContent':
                    if not isinstance(retry_tokens, int) or retry_tokens <= 0:
                        raise GemmaServiceError('Gemma : relance impossible sans comptage de jetons. Arrêt prudent.') from None
                    _reserve(retry_tokens)
                continue
            detail = ('Erreur serveur persistante après 3 tentatives.' if code in {500,502,503,504}
                else 'Requête ou accès refusé, sans relance.')
            error_type = GemmaTransientError if code in {500, 502, 503, 504} else GemmaServiceError
            raise error_type(f'Gemma : HTTP {code} ({status}) lors de {method}. '
                + detail + ' Diagnostic local : data/_ai/gemma_failures.json.') from None
        except (URLError, TimeoutError, OSError):
            # La génération peut avoir été exécutée avant une coupure réseau.
            raise GemmaTransientError('Gemma : connexion indisponible ou délai dépassé. Contrôle différable ; étapes sauvegardées conservées.') from None


@contextmanager
def _locked(path):
    """Verrou Windows/Linux : le site et le CLI partagent la même réserve."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _THREAD_LOCK, path.open('a+b') as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.2)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _reserve(tokens, path=None):
    if tokens > TPM:
        raise AIInputTooLargeError(f'Gemma : cet appel contient {tokens} jetons d’entrée, '
            f'au-delà du budget prudent de {TPM}/minute. Aucune source tronquée. '
            'Traitement interrompu : examiner et découper ce passage avant reprise.')
    path = path or DATA_DIR / '_ai' / 'gemma_rate.json'
    announced = False
    while True:
        with _locked(path.with_suffix('.lock')):
            try:
                entries = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
                if not isinstance(entries, list) or any(not isinstance(i, list) or len(i) != 2
                    or not isinstance(i[0], (int, float)) or not isinstance(i[1], int) or i[1] < 0 for i in entries):
                    raise ValueError()
            except (ValueError, OSError):
                raise AIUsageLimitError('Réserve de débit Gemma illisible : arrêt sans effacement. '
                    'Attendre au moins 61 secondes après le dernier appel avant de réparer ce fichier.') from None
            now = time.time()
            entries = [i for i in entries if now - i[0] < WINDOW]
            if len(entries) < RPM and sum(i[1] for i in entries) + tokens <= TPM:
                entries.append([now, tokens])
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                    delete=False) as handle:
                    json.dump(entries, handle); temporary = Path(handle.name)
                try:
                    os.replace(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)
                return
            delay = max(0.2, min(30, WINDOW - (now - min(i[0] for i in entries))))
        if not announced:
            print('Gemma : attente du budget de jetons/minute…', flush=True)
            announced = True
        time.sleep(delay)


def _parts(message):
    parts = []
    content = message.get('content', '')
    if not isinstance(content, str):
        raise ValueError('Gemma attend un contenu texte.')
    if content:
        parts.append({'text': content})
    for value in message.get('images', []):
        if isinstance(value, bytes):
            raw = value
        elif isinstance(value, str) and len(value) < 240 and '\x00' not in value and Path(value).is_file():
            raw = Path(value).read_bytes()
        elif isinstance(value, str):
            raw = base64.b64decode(value, validate=True)
        else:
            raise ValueError('Image Gemma invalide.')
        if raw.startswith(b'\x89PNG\r\n\x1a\n'):
            mime = 'image/png'
        elif raw.startswith(b'\xff\xd8\xff'):
            mime = 'image/jpeg'
        elif raw.startswith(b'RIFF') and raw[8:12] == b'WEBP':
            mime = 'image/webp'
        else:
            raise ValueError('Gemma : image PNG, JPEG ou WebP requise.')
        parts.append({'inlineData': {'mimeType': mime, 'data': base64.b64encode(raw).decode('ascii')}})
    return parts or [{'text': ''}]


def gemma_chat(*, messages, model, format=None, options=None, think=None):
    if model not in MODELS:
        raise GemmaServiceError('Le fournisseur gemma attend gemma-4-31b-it ou gemma-4-26b-a4b-it. '
            'Ne pas conserver un identifiant de modèle Ollama dans STUDYPILOT_MODEL.')
    contents = []; instructions = []
    for message in messages:
        role = message.get('role')
        if role == 'system':
            instructions.extend(_parts(message))
        elif role in {'user', 'assistant'}:
            contents.append({'role': 'model' if role == 'assistant' else 'user', 'parts': _parts(message)})
        else:
            raise ValueError('Rôle de message non pris en charge par Gemma.')
    if format is not None and not any('SCHÉMA JSON DE LA RÉPONSE' in p.get('text', '') for p in instructions):
        instruction = 'Réponds avec un objet JSON complet, sans Markdown ni commentaire.'
        if isinstance(format, dict):
            instruction += '\nSchéma à respecter : ' + json.dumps(format, ensure_ascii=False)
        instructions.append({'text': instruction})
    if not contents:
        raise ValueError('Gemma : au moins un message utilisateur requis.')
    payload = {'contents': contents}
    if instructions:
        payload['systemInstruction'] = {'parts': instructions}
    # countTokens reçoit le même contenu et les mêmes instructions que la génération.
    counted = _post(model, 'countTokens', {'generateContentRequest': {
        'model': 'models/' + model, **payload}})
    count = counted.get('totalTokens')
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise GemmaServiceError('Gemma : comptage de jetons invalide, aucun appel de génération lancé.')
    _reserve(count)
    opts = options or {}
    payload['generationConfig'] = {'temperature': opts.get('temperature', 0.1),
        'maxOutputTokens': opts.get('num_predict', 5000),
        'thinkingConfig': {'thinkingLevel': 'high' if think in (True, 'high') else 'minimal'}}
    response = _post(model, 'generateContent', payload, retry_tokens=count)
    candidates = response.get('candidates') or []
    if not candidates:
        raise ValueError('Gemma : aucune réponse exploitable (blocage ou absence de candidat).')
    candidate = candidates[0]
    if candidate.get('finishReason') not in {'STOP', None}:
        raise ValueError('Gemma : réponse non terminée normalement : ' + str(candidate.get('finishReason')))
    text = ''.join(p['text'] for p in candidate.get('content', {}).get('parts', [])
        if isinstance(p.get('text'), str) and not p.get('thought'))
    return SimpleNamespace(message=SimpleNamespace(content=text))
