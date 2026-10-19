"""Client IA unique de StudyPilot.

Aucun autre module métier ne doit importer ``ollama`` directement.
"""

from __future__ import annotations

from pydantic import BaseModel
import json
import re
from collections.abc import Callable
from typing import Any
from src.ai.workload import serialized, request_attempt

from src.config import (
    AI_PROVIDER,
    AI_KEEP_ALIVE,
    AI_NUM_CTX,
    AI_THINK,
    DEFAULT_TEMPERATURE,
    STUDY_MODEL,
)


class AIUnavailableError(RuntimeError):
    """Le client local Ollama n'est pas disponible."""


class AIUsageLimitError(RuntimeError):
    """Le fournisseur refuse de nouveaux appels ; interrompre la passe sans relance."""


class AITransientError(AIUsageLimitError):
    """Panne serveur : différable uniquement à une frontière de notion sauvegardée."""


class AIInputTooLargeError(AIUsageLimitError):
    """Une requête dépasse le budget ; seul un découpage des sources peut aider."""


def _ollama_chat() -> Callable[..., Any]:
    try:
        from ollama import chat as ollama_chat
    except ImportError as error:
        raise AIUnavailableError(
            "Ollama n'est pas installé. "
            "Installe les dépendances puis vérifie "
            "le serveur local."
        ) from error

    return ollama_chat


@serialized
def chat(
    *,
    messages: list[dict],
    model: str | None = None,
    format: str | dict[str, Any] | None = None,
    options: dict | None = None,
    think: bool | str | None = None,
    keep_alive: str | None = None,
):
    """Exécute un appel Ollama avec les réglages StudyPilot."""

    merged_options: dict[str, Any] = {
        "temperature": DEFAULT_TEMPERATURE,
        "num_ctx": AI_NUM_CTX,
    }

    if options:
        merged_options.update(options)

    if AI_PROVIDER == "gemma":
        from src.ai.gemma import gemma_chat
        return gemma_chat(messages=messages, model=model or STUDY_MODEL,
                          format=format, options=merged_options,
                          think=AI_THINK if think is None else think)
    if AI_PROVIDER == 'gemini':
        from src.ai.gemini import gemini_chat
        return gemini_chat(messages=messages,model=model or STUDY_MODEL,format=format,options=merged_options,
                           think=AI_THINK if think is None else think)
    if AI_PROVIDER != "ollama":
        raise AIUnavailableError("STUDYPILOT_AI_PROVIDER doit être ollama, gemma ou gemini.")

    kwargs: dict[str, Any] = {
        "model": model or STUDY_MODEL,
        "messages": messages,
        "options": merged_options,
        "think": AI_THINK if think is None else think,
        "keep_alive": (
            AI_KEEP_ALIVE
            if keep_alive is None
            else keep_alive
        ),
    }

    if format is not None:
        kwargs["format"] = format

    try:
        request_attempt(sum(len(str(m.get('content', ''))) for m in messages)//3,
                        int(merged_options.get('num_predict', 5000)))
        return _ollama_chat()(**kwargs)
    except Exception as error:
        if getattr(error, 'status_code', None) == 429 or 'monthly usage limit' in str(error).casefold():
            raise AIUsageLimitError('Ollama a refusé les appels (quota / HTTP 429). '
                'Traitement interrompu ; conserver les checkpoints et reprendre quand l’accès est disponible. '
                + str(error)) from error
        raise


def _response_text(response: Any) -> str:
    message = getattr(response, "message", None)
    content = getattr(message, "content", None)

    if not isinstance(content, str):
        raise ValueError(
            "Réponse IA sans contenu texte exploitable."
        )

    return content.strip()

_LATEX_JSON_COMMANDS = {
    "alpha",
    "beta",
    "gamma",
    "delta",
    "epsilon",
    "theta",
    "lambda",
    "mu",
    "nu",
    "pi",
    "rho",
    "sigma",
    "phi",
    "omega",
    "frac",
    "tfrac",
    "dfrac",
    "sqrt",
    "sum",
    "prod",
    "int",
    "iint",
    "iiint",
    "cos",
    "sin",
    "tan",
    "exp",
    "log",
    "ln",
    "lim",
    "infty",
    "partial",
    "nabla",
    "forall",
    "exists",
    "in",
    "notin",
    "le",
    "leq",
    "ge",
    "geq",
    "neq",
    "approx",
    "sim",
    "to",
    "rightarrow",
    "leftarrow",
    "mapsto",
    "times",
    "cdot",
    "pm",
    "mp",
    "left",
    "right",
    "mathbb",
    "mathrm",
    "mathbf",
    "mathcal",
    "operatorname",
    "text",
    "overline",
    "underline",
    "bar",
    "hat",
    "vec",
    "begin",
    "end",
}


def _protect_latex_backslashes_in_json(
    text: str,
) -> str:
    """
    Répare les antislashs LaTeX que certains modèles
    oublient d'échapper dans une chaîne JSON.

    Exemple invalide :
        "\\(x\\)" avec un seul antislash dans le JSON brut

    Exemple JSON correct :
        "\\\\(x\\\\)"

    Les séquences JSON normales comme \\n restent intactes.
    """

    result: list[str] = []

    index = 0
    in_string = False
    length = len(text)

    while index < length:
        char = text[index]

        if char == '"':
            in_string = not in_string
            result.append(char)
            index += 1
            continue

        if not in_string or char != "\\":
            result.append(char)
            index += 1
            continue

        if index + 1 >= length:
            result.append("\\\\")
            index += 1
            continue

        next_char = text[index + 1]

        # Déjà correctement échappé en JSON.
        if next_char in {'"', "\\", "/"}:
            result.append(char)
            result.append(next_char)
            index += 2
            continue

        # Délimiteurs LaTeX : \( \) \[ \]
        if next_char in {"(", ")", "[", "]"}:
            result.append("\\\\")
            index += 1
            continue

        if next_char.isalpha():
            match = re.match(
                r"[A-Za-z]+",
                text[index + 1:],
            )

            command = (
                match.group(0)
                if match is not None
                else ""
            )

            if command in _LATEX_JSON_COMMANDS:
                result.append("\\\\")
                index += 1
                continue

        # Échappements JSON standards.
        if next_char in {"b", "f", "n", "r", "t"}:
            result.append(char)
            result.append(next_char)
            index += 2
            continue

        if next_char == "u":
            hexadecimal = text[
                index + 2:index + 6
            ]

            if (
                len(hexadecimal) == 4
                and all(
                    character in "0123456789abcdefABCDEF"
                    for character in hexadecimal
                )
            ):
                result.append(char)
                result.append(next_char)
                index += 2
                continue

        # Tout autre antislash est invalide en JSON,
        # mais très probablement légitime en LaTeX.
        result.append("\\\\")
        index += 1

    return "".join(result)

def chat_text(**kwargs) -> str:
    """Retourne directement le texte d'une réponse Ollama."""

    return _response_text(chat(**kwargs))


def readable_contract(schema, root=None, depth=0):
    """Contrat lisible sans l'enveloppe properties/required souvent recopiée."""
    root = root or schema
    if depth > 10:
        return 'valeur respectant le contrat'
    if '$ref' in schema:
        target = root
        for key in schema['$ref'].removeprefix('#/').split('/'):
            target = target[key]
        return readable_contract(target, root, depth+1)
    if 'enum' in schema:
        return 'une des valeurs ' + json.dumps(schema['enum'], ensure_ascii=False)
    if 'const' in schema:
        return 'exactement ' + json.dumps(schema['const'], ensure_ascii=False)
    if 'anyOf' in schema:
        return ' ou '.join(readable_contract(x,root,depth+1) for x in schema['anyOf'])
    kind = schema.get('type')
    if kind == 'object':
        fields = schema.get('properties', {})
        if not fields:
            keys = readable_contract(schema['propertyNames'],root,depth+1) if 'propertyNames' in schema else 'clés textuelles'
            value = schema.get('additionalProperties', {})
            return 'dictionnaire ('+keys+') vers '+readable_contract(value,root,depth+1) if isinstance(value,dict) else 'objet sans champs supplémentaires'
        required=set(schema.get('required', []))
        return 'objet avec ces champs seulement : {' + '; '.join(k + (' [obligatoire]' if k in required else ' [optionnel]') + ' : ' + readable_contract(v,root,depth+1) for k,v in fields.items()) + '}'
    if kind == 'array':
        return 'liste de '+readable_contract(schema.get('items',{}),root,depth+1)
    return {'string':'texte','integer':'entier','number':'nombre','boolean':'true ou false','null':'null'}.get(kind,'valeur JSON')


def chat_json(
    *,
    response_model: type[BaseModel] | None = None,
    **kwargs,
) -> dict:
    """Retourne un JSON validé, éventuellement contraint par un modèle Pydantic."""

    if response_model is not None:
        schema = response_model.model_json_schema()
        kwargs["format"] = schema

        # Les modèles cloud ne garantissent pas le paramètre format.
        # Le contrat doit donc aussi être visible dans les instructions,
        # tout en gardant la validation Pydantic après génération.
        schema_instruction = (
            "SCHÉMA JSON DE LA RÉPONSE :\n"
            + (readable_contract(schema) if AI_PROVIDER == "gemma" else json.dumps(schema, ensure_ascii=False))
            + "\nRespecte exactement ce schéma : noms des champs, types, "
            "listes et valeurs autorisées. Réponds avec un objet JSON complet, "
            "sans balises Markdown ni commentaire. Le schéma est une description du contrat, "
            "PAS la réponse : ne recopie jamais properties, required, $defs ni le schéma lui-même. "
            "Produis les valeurs des champs demandés à partir des sources."
        )
        messages = [dict(message) for message in kwargs.get("messages", [])]
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = (
                messages[0]["content"] + "\n\n" + schema_instruction
            )
        else:
            messages.insert(0, {"role": "system", "content": schema_instruction})
        kwargs["messages"] = messages
    else:
        kwargs.setdefault("format", "json")

    text = chat_text(**kwargs)

    if not text.strip():
        # Certains modèles consomment le budget avant d'émettre le JSON.
        # Une seule relance bornée, même modèle, aucune réponse fabriquée.
        retry_kwargs = dict(kwargs)
        retry_options = dict(kwargs.get("options") or {})
        budget = retry_options.get("num_predict", 2200)
        retry_options["num_predict"] = min(8192, max(4096, budget * 2))
        retry_kwargs["options"] = retry_options
        text = chat_text(**retry_kwargs)
        if not text.strip():
            raise ValueError("Le modèle a retourné deux réponses JSON vides ; génération à reprendre.")

    return parse_json_response(text, response_model=response_model)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Clé JSON dupliquée : {key}. Regrouper les éléments dans une seule liste ; aucune valeur ne doit être écrasée.")
        result[key] = value
    return result


def parse_json_response(text: str, *, response_model=None) -> dict:
    """Même lecture pour plan, aperçus et fiches ; aucun choix silencieux entre deux valeurs."""
    schema = response_model.model_json_schema() if response_model is not None else None
    text = _protect_latex_backslashes_in_json(
        text
    )

    # Accepter un unique bloc JSON balisé, pas du texte entourant plusieurs
    # réponses. Ne jamais choisir arbitrairement le premier objet concaténé.
    fenced = re.fullmatch(r'```(?:json)?\s*\n?(.*?)\s*```', text, flags=re.S)
    if fenced and '```' not in fenced.group(1):
        text = fenced.group(1)

    if response_model is not None:
        # Quelques modèles préfixent la réponse par le schéma fourni. Retirer
        # uniquement cet objet exact, jamais choisir parmi plusieurs réponses.
        original_text = text
        prefix_fence = re.match(r'```(?:json)?\s*\n?(.*?)\s*```\s*', text, flags=re.S)
        echo_text = prefix_fence.group(1) if prefix_fence else text
        try:
            echoed, offset = json.JSONDecoder().raw_decode(echo_text)
        except ValueError:
            echoed, offset = None, 0
        if echoed == schema:
            # Un bloc balisé doit contenir seulement le schéma exact.
            if prefix_fence and echo_text[offset:].strip():
                echoed = None
        if echoed == schema:
            remainder = text[prefix_fence.end() if prefix_fence else offset:].strip()
            if not remainder:
                error = ValueError('Le modèle a recopié le schéma JSON au lieu de fournir les valeurs des champs. Répondre avec une instance du contrat, sans recopier le schéma.')
                error.response_text = original_text[:6000]
                raise error
            text = remainder
            answer_fence = re.fullmatch(r'```(?:json)?\s*\n?(.*?)\s*```', text, flags=re.S)
            if answer_fence:
                text = answer_fence.group(1)
        try:
            # Pydantic et json.loads acceptent normalement la dernière valeur
            # d'une clé répétée. Un modèle ne doit pas effacer des notions ainsi.
            try:
                json.loads(text, object_pairs_hook=_unique_object)
            except json.JSONDecodeError:
                pass  # Pydantic fournit ensuite l'erreur structurée habituelle.
            validated = response_model.model_validate_json(text)
        except ValueError as error:
            # Conserver la classe ValidationError et ses erreurs structurées :
            # les reprises de l'inventaire s'en servent pour corriger les champs.
            error.response_text = original_text[:6000]
            raise
        return validated.model_dump(mode="json")

    data = json.loads(text, object_pairs_hook=_unique_object)

    if not isinstance(data, dict):
        raise ValueError(
            "La réponse IA JSON doit être un objet."
        )

    return data
