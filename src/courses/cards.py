"""Génération des fiches pédagogiques à partir de l'inventaire validé."""

from __future__ import annotations

from src.ai.client import AIUsageLimitError

import hashlib
import json
import re
import unicodedata

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
)

from src.courses.card_presentation import publication_issue, publication_view
from src.courses.pedagogy import prepare_material, QUALITY_VERSION, backup, issue_blocks_concept, issue_affects_part
from src.ai.client import chat_json
from src.config import COURSE_PDF_DIR, STUDY_MODEL
from src.courses.planner import extract_document
from src.courses.service import load_course, load_course_plan
from src.courses.card_grounding import audit_cards, code_issue, proof_issue, source_code_snippets, same_literal_code
from src.models.card import (
    BlockedCard,
    CardCollection,
    CardPartCoverage,
    CardSection,
    StudyCard,
)
from src.models.concept import Concept, ConceptInventory
from src.storage.course_repository import CourseRepository
from src.storage.repository import StorageError

class _AICardSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=1,
        max_length=120,
    )
    content: str = Field(
        default="",
        max_length=6000,
    )
    source_ref: str | None = Field(default=None, min_length=1, description="Null ou omis pour la prose. Pour le code : identifiant code-N du catalogue de cette notion, avec content vide.")


class _AICard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_id: str = Field(
        min_length=1,
        max_length=140,
    )
    sections: list[_AICardSection] = Field(
        min_length=1,
        max_length=8,
    )


class _AICardBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cards: list[_AICard]


class CardGenerationError(ValueError):
    """Conserve les fiches validées même si d'autres notions du lot échouent."""
    def __init__(self, message, generated, failures):
        super().__init__(message)
        self.generated = list(generated)
        self.failures = failures

def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value).casefold())
    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    return re.sub(r"[^a-z0-9]+", " ", text).strip()

def _source_text(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        unicodedata.normalize("NFKC", str(value)).casefold(),
    ).strip()


def _loose_source_text(value: str) -> str:
    text = unicodedata.normalize(
        "NFKD",
        str(value).casefold(),
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    return re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    ).strip()


def _excerpt_is_grounded(
    excerpt: str,
    page: dict,
) -> bool:
    needle = _source_text(excerpt)

    if len(needle) < 3:
        return False

    for field in ("raw_text", "analysis_text"):
        haystack = _source_text(
            str(page.get(field) or "")
        )

        if needle in haystack:
            return True

    loose_needle = _loose_source_text(excerpt)

    if len(loose_needle) < 3:
        return False

    for field in ("raw_text", "analysis_text"):
        haystack = _loose_source_text(
            str(page.get(field) or "")
        )

        if loose_needle in haystack:
            return True

    return False

_GREEK_LATEX = {
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\delta": "δ",
    r"\epsilon": "ε",
    r"\theta": "θ",
    r"\lambda": "λ",
    r"\mu": "μ",
    r"\pi": "π",
    r"\sigma": "σ",
    r"\phi": "φ",
    r"\omega": "ω",
}


def _math_signatures(value: str) -> set[str]:
    """
    Extrait uniquement les vraies notations sensibles.

    Les commandes LaTeX comme \\in, \\frac, \\mathbb,
    \\cos, \\sin, etc. ne doivent jamais être prises
    pour des variables mathématiques.
    """

    text = str(value).replace("−", "-")

    # On convertit d'abord les symboles LaTeX que l'on
    # veut réellement comparer.
    for latex, symbol in _GREEK_LATEX.items():
        text = text.replace(latex, symbol)

    # Puis on retire les noms de commandes LaTeX.
    #
    # Exemples :
    #   a_n \\in \\mathbb{C}
    # devient approximativement :
    #   a_n {C}
    #
    # Ainsi "\\in" ne peut plus devenir la fausse
    # signature "in".
    text = re.sub(
        r"\\[A-Za-z]+",
        " ",
        text,
    )

    signatures: set[str] = set()

    # a_n, c_{-n}, A_0...
    for match in re.finditer(
        r"([A-Za-z])_\{?(-?[A-Za-z0-9]+)\}?",
        text,
    ):
        signatures.add(
            f"{match.group(1)}{match.group(2)}"
        )

    # Formes issues de l'extraction PDF :
    # an, bn, cn, a0...
    for match in re.finditer(
        r"(?<![A-Za-z])([A-Za-z])(-?n|\d+)(?![A-Za-z])",
        text,
    ):
        signatures.add(
            f"{match.group(1)}{match.group(2)}"
        )

    for symbol in (
        "α",
        "β",
        "γ",
        "δ",
        "ε",
        "θ",
        "λ",
        "μ",
        "π",
        "σ",
        "φ",
        "ω",
    ):
        if symbol in text:
            signatures.add(symbol)

    return signatures


def _contains_math(value: str) -> bool:
    text = str(value)

    return any(
        marker in text
        for marker in (
            r"\(",
            r"\[",
            "$",
            r"\frac",
            r"\sum",
            r"\int",
        )
    )


def _compact_math_text(value: str) -> str:
    text = str(value).replace("−", "-")

    for latex, symbol in _GREEK_LATEX.items():
        text = text.replace(latex, symbol)

    replacements = {
        r"\cos": "cos",
        r"\sin": "sin",
        r"\tan": "tan",
        r"\exp": "exp",
        r"\left": "",
        r"\right": "",
        r"\,": "",
        r"\;": "",
        r"\!": "",
        r"\quad": "",
        r"\qquad": "",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = (
        text.replace("_", "")
        .replace("{", "")
        .replace("}", "")
    )

    return re.sub(
        r"[^A-Za-z0-9α-ωΑ-Ω+\-]",
        "",
        text,
    )


def _generated_math_text(value: str) -> str:
    """
    Isole uniquement les expressions mathématiques générées.

    Le texte pédagogique normal ne doit jamais être interprété
    comme de la notation mathématique. Par exemple les mots
    français "un", "en" ou "on" ne doivent pas devenir
    artificiellement u_n, e_n ou o_n.
    """

    text = str(value)
    fragments: list[str] = []

    fragments.extend(
        re.findall(
            r"\\\((.*?)\\\)",
            text,
            flags=re.DOTALL,
        )
    )

    fragments.extend(
        re.findall(
            r"\\\[(.*?)\\\]",
            text,
            flags=re.DOTALL,
        )
    )

    fragments.extend(
        re.findall(
            r"\$(.*?)\$",
            text,
            flags=re.DOTALL,
        )
    )

    if fragments:
        return "\n".join(fragments)

    # Compatibilité avec une éventuelle formule LaTeX
    # produite sans délimiteur.
    return text


def _math_is_supported(
    content: str,
    source_text: str,
) -> tuple[bool, str | None]:
    """
    Vérifie que les notations mathématiques générées sont
    supportées par la source et explique précisément un rejet.

    Ce garde-fou ne démontre pas une équivalence mathématique.
    Il empêche surtout le modèle d'introduire librement de
    nouvelles variables ou structures sensibles.
    """

    if not _contains_math(content):
        return True, None

    generated_math = _generated_math_text(content)

    generated = _math_signatures(generated_math)
    source = _math_signatures(source_text)

    unsupported = sorted(generated - source)

    if unsupported:
        return (
            False,
            "notations absentes de la source : "
            + ", ".join(unsupported),
        )

    source_compact = _compact_math_text(
        source_text
    )

    # Quand la source contient déjà du LaTeX explicite, conserver la structure
    # exacte au lieu de comparer seulement les noms des variables. Aucun calcul
    # d'équivalence : les fractions, signes et indices restent significatifs.
    expression = r"\\\[(.*?)\\\]|\\\((.*?)\\\)|\$\$(.*?)\$\$|(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)"
    def formulas(value):
        return [next(part for part in match if part) for match in re.findall(expression, value, re.S) if any(match)]
    def canonical(value):
        for latex, symbol in _GREEK_LATEX.items():
            value = value.replace(latex, symbol)
        value = re.sub(r"\\(?:left|right|quad|qquad)\b|\\[,;!]", "", value)
        return re.sub(r"\s+", "", value).replace('−', '-')
    originals = formulas(source_text)
    if originals:
        for formula in formulas(content):
            if not any(canonical(formula) in canonical(source) for source in originals):
                return False, "formule différente de la source (fraction, signe, indice ou structure)"
    # Sur texte natif, vérifier les arguments effectivement générés plutôt
    # qu'une liste de formules appartenant à un cours particulier.
    for fragment in re.findall(r"(?:\\(?:sin|cos|tan|exp)\s*\([^)]*\)|[A-Za-z]\^\{[^}]+\})", generated_math):
        if _compact_math_text(fragment) not in source_compact:
            return False, "structure mathématique absente de la source : " + fragment

    return True, None



def _section_key(value: str) -> str:
    key = re.sub(
        r"[^a-z0-9]+",
        "_",
        _norm(value),
    ).strip("_")

    return key[:80] or "section"


_ENGLISH_MARKERS = {
    "the",
    "and",
    "is",
    "are",
    "can",
    "be",
    "with",
    "within",
    "from",
    "for",
    "of",
    "on",
    "this",
    "that",
    "these",
    "those",
    "when",
    "which",
    "uses",
    "used",
    "using",
    "to",
    "as",
    "by",
    "or",
}

_FRENCH_MARKERS = {
    "le",
    "la",
    "les",
    "un",
    "une",
    "des",
    "du",
    "de",
    "et",
    "est",
    "sont",
    "peut",
    "peuvent",
    "avec",
    "dans",
    "sur",
    "pour",
    "par",
    "ce",
    "cette",
    "ces",
    "qui",
    "que",
    "lorsque",
    "utilise",
    "utilisee",
    "utilisees",
}


def _language_tokens(value: str) -> list[str]:
    """
    Retire maths, code et balises avant d'évaluer
    la langue de la prose pédagogique.
    """

    text = str(value)

    text = re.sub(
        r"\\\[[\s\S]*?\\\]",
        " ",
        text,
    )

    text = re.sub(
        r"\\\([\s\S]*?\\\)",
        " ",
        text,
    )

    text = re.sub(
        r"`[^`]*`",
        " ",
        text,
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    return _norm(text).split()


def _looks_mostly_english(value: str) -> bool:
    tokens = _language_tokens(value)

    english = sum(
        token in _ENGLISH_MARKERS
        for token in tokens
    )

    french = sum(
        token in _FRENCH_MARKERS
        for token in tokens
    )

    return (
        english >= 4
        and english >= french + 2
    )


def _section_is_too_dense(value: str) -> bool:
    """
    Une fiche est faite pour réviser,
    pas pour reproduire un paragraphe du cours.
    """

    tokens = _language_tokens(value)
    return len(tokens) > 110



def _card_id(concept_id: str) -> str:
    digest = hashlib.sha256(
        concept_id.encode("utf-8")
    ).hexdigest()[:16]

    return f"card-{digest}"


def _inventory_hash(inventory: ConceptInventory) -> str:
    payload = json.dumps(
        inventory.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


def _concept_hash(concept: Concept) -> str:
    payload = concept.model_dump(mode="json")
    # L'ajout d'un champ optionnel vide ne périme pas les fiches v10.
    if not payload.get("learning_points"):
        payload.pop("learning_points", None)
    if payload.get("card_role") == "standalone":
        payload.pop("card_role", None)
    if not payload.get("illustrations"):
        payload.pop("illustrations", None)
    if payload.get("illustrations"):
        payload["written_visual_protocol"] = 1
    if payload.get("relevance") == "active":
        payload.pop("relevance", None)
    for field in ("relevance_reason", "relevance_file_hash", "relevance_proof_hash"):
        if payload.get(field) is None:
            payload.pop(field, None)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _part_pages(document: dict, part: dict) -> list[dict]:
    start = int(part["page_start"])
    end = int(part["page_end"])

    return [
        page
        for page in document["pages"]
        if start <= int(page["page"]) <= end
    ]

def _concept_pages(
    document: dict,
    concepts: list[Concept],
) -> list[dict]:
    wanted = {
        page_number
        for concept in concepts
        for page_number in concept.source_pages
    }

    return [
        page
        for page in document["pages"]
        if int(page["page"]) in wanted
    ]


def _part_source(part: dict, pages: list[dict]) -> str:
    blocks: list[str] = []

    for page in pages:
        blocks.append(
            f"[PAGE PHYSIQUE {page['page']}]\n"
            f"{page.get('analysis_text') or page.get('raw_text') or ''}"
        )

    return (
        f"PARTIE {part['number']} — {part['title']}\n\n"
        + "\n\n".join(blocks)
    )


def _clean_card_evidence(excerpt: str) -> str:
    """
    Nettoie uniquement des artefacts d'extraction PDF connus
    avant d'envoyer une preuve au modèle.

    On ne modifie pas l'inventaire sauvegardé et on n'invente
    aucune information pédagogique.
    """

    return str(excerpt).strip()



def _concept_description(concept: Concept) -> str:
    evidence = "\n".join(
        (
            f"  - p.{item.page}: "
            f"{_clean_card_evidence(item.excerpt)}"
        )
        for item in concept.evidence
    )

    pages = ", ".join(
        str(page)
        for page in concept.source_pages
    )

    return (
        f"CONCEPT_ID: {concept.concept_id}\n"
        f"TITRE: {concept.title}\n"
        f"TYPE: {concept.type}\n"
        f"POINTS PÉDAGOGIQUES À COUVRIR (même ordre que les PREUVES) : {json.dumps([{'id': p.point_id, 'kind': p.kind, 'page': p.page} for p in concept.learning_points], ensure_ascii=False)}\n"
        f"PAGES SOURCES: {pages}\n"
        f"PREUVES:\n{evidence}\n"
        f"EXTRAITS DE CODE À SÉLECTIONNER PAR source_ref :\n{json.dumps(source_code_snippets(concept), ensure_ascii=False)}"
        + ("\nAUCUN EXTRAIT DE CODE : restitue les explications en prose et les formules attestées en LaTeX, avec source_ref null. Ne convertis pas un nom en balise ou en commande."
           if not source_code_snippets(concept) else "")
    )



def _cards_prompt(
    part: dict,
    pages: list[dict],
    concepts: list[Concept],
) -> str:
    """
    Construit le prompt de génération.

    Les evidence validées de chaque Concept constituent la seule
    matière pédagogique visible par le modèle.

    Les pages complètes restent disponibles côté StudyPilot pour
    les contrôles automatiques, mais ne sont pas données au modèle
    comme contenu à résumer.
    """

    requested = "\n\n".join(
        _concept_description(concept)
        for concept in concepts
    )

    verification_pages = sorted({
        page_number
        for concept in concepts
        for page_number in concept.source_pages
    })

    page_text = ", ".join(
        str(page_number)
        for page_number in verification_pages
    )

    return (
        "Tu construis des fiches de révision StudyPilot "
        "strictement à partir des PREUVES validées fournies ci-dessous.\n\n"

        "SOURCE : chaque CONCEPT_ID possède ses propres PREUVES. "
        "Ces PREUVES sont la seule matière pédagogique que tu as "
        "le droit d'utiliser pour cette fiche. "
        "N'utilise jamais tes connaissances générales et ne complète "
        "jamais une notion à partir de ce que tu sais déjà.\n\n"

        "IMPORTANT : les preuves d'un CONCEPT_ID ne doivent jamais "
        "servir à enrichir la fiche d'un autre CONCEPT_ID. "
        "Chaque fiche reste strictement centrée sur sa notion.\n\n"

        "Ne développe pas une section voisine du cours simplement "
        "parce qu'elle est logiquement liée à la notion. "
        "Les points rattachés par l'analyse pédagogique font partie de la fiche : "
        "conserve leurs exemples, conseils et conditions en sections distinctes.\n\n"

        "Couvre tous les POINTS PÉDAGOGIQUES, en regroupant les répétitions. "
        "Le titre définit le périmètre de la fiche. Une citation peut inclure du contexte sur d'autres notions : "
        "restitue ce qu'elle enseigne sur la notion annoncée, sans recopier tout le cours voisin. "
        "Une fiche sur un paramètre explique le paramètre et son rôle dans l'exemple, "
        "elle ne devient pas une seconde fiche générale sur les fonctions. "
        "Le même principe s'applique à toute matière et à toute sous-notion. "
        "Définition, conditions et exemple doivent être exploités quand ils existent. "
        "Ne transforme pas des choix alternatifs en étapes numérotées. "
        "Une propriété ou commande exige son rôle et son usage quand le cours les fournit. "
        "Les conseils rattachés restent une section Conseils, pas une règle générale.\n\n"

        "LANGUE : toute la prose pédagogique doit être en français, "
        "même si le PDF source est rédigé en anglais. "
        "Une phrase explicative entièrement en anglais est interdite. "
        "Traduis l'explication, mais conserve exactement les éléments "
        "techniques qui ne doivent pas être traduits : code, syntaxe, "
        "commandes, sélecteurs, propriétés, identifiants, noms d'API "
        "et notations mathématiques.\n\n"

        "Crée EXACTEMENT UNE fiche pour chaque CONCEPT_ID. "
        "N'ajoute aucune notion et n'en oublie aucune.\n\n"

        "Tu n'as PAS à recopier les preuves ni les numéros de page "
        "dans le JSON. StudyPilot connaît déjà leur provenance.\n\n"

        "MATHÉMATIQUES : une formule ne peut être utilisée que si elle "
        "est explicitement présente dans les PREUVES de la notion. "
        "Tu peux uniquement la transcrire proprement en LaTeX. "
        "Ne la généralise pas, ne la spécialise pas et ne change jamais "
        "les variables, coefficients, indices, bornes, constantes ou "
        "conventions.\n\n"

        "Ne transforme jamais a_n en A_n, b_n en B_n, "
        "c_n en a_n, etc. "
        "Ne remplace jamais T ou ω par une valeur particulière si la "
        "preuve ne le fait pas.\n\n"

        "Les formules importantes utilisent "
        "\\[ ... \\] et les petites expressions \\( ... \\). "
        "N'utilise pas $...$.\n\n"

        "LISIBILITÉ MATHÉMATIQUE : une formule importante ne doit jamais "
        "être noyée au milieu d'un paragraphe. "
        "Place-la seule dans une section Formule avec \\\\[ ... \\\\]. "
        "Si le PDF explique ce que signifient ses symboles ou son rôle, "
        "place cette explication dans une section séparée nommée "
        "'Signification' ou 'À retenir'. "
        "N'invente jamais une interprétation absente des sources.\n\n"

        "Privilégie une explication, définition ou condition lorsque les PREUVES la fournissent. "
        "Une syntaxe, formule, liste contextualisée ou illustration attestée peut aussi être un support utile. "
        "Ne complète jamais un extrait avec une explication absente des PREUVES.\n"
        "STRUCTURE ADAPTATIVE :\n"
        "Le nombre de sections dépend du contenu à enseigner, sans remplissage. "
        "Chaque section porte un titre informatif (Définition, Hypothèses, Résultat, "
        "Méthode, Exemple ou Limite selon le contenu), pas un paragraphe fourre-tout. "
        "Une seule idée par paragraphe, des phrases directes et des listes pour les conditions distinctes. "
        "Évite les introductions 'le cours présente' et les répétitions entre sections. "
        "Ne raccourcis jamais une hypothèse, une exception ou une justification nécessaire. "
        "N'ajoute ni formule ni exemple pour embellir une fiche rédactionnelle. "
        "Le catalogue de code est un choix d'extraits, pas une liste à recopier intégralement.\n"
        "- Définition/Concept : une section Définition courte ; "
        "ajoute éventuellement Explication ou À retenir uniquement si "
        "les sources le permettent.\n"
        "- Théorème : Énoncé, puis Conditions et Conséquence "
        "si elles sont réellement présentes.\n"
        "- Propriété technique : rôle, utilisation, valeurs et mini exemple lorsque les preuves les fournissent.\n"
        "- Formule : section Formule contenant principalement la formule, "
        "puis Signification si le cours l'explique.\n"
        "- Méthode/Protocole : Objectif puis Étapes courtes.\n"
        "- Syntaxe/Commande : Syntaxe originale inchangée, puis "
        "Explication en français.\n"
        "- Exemple : uniquement l'exemple réellement fourni par le cours.\n\n"

        "CODE : recopie uniquement le code présent dans les preuves de cette notion. "
        "Pour un extrait du catalogue, utilise une section avec title='Exemple du cours', "
        "source_ref='code-N' et content=''. Python recopiera cet extrait sans le modifier. "
        "Ne réduis pas la fiche au code quand des explications sont disponibles. "
        "Si les preuves sont uniquement des explications, garde une fiche en prose : "
        "Si la preuve est une phrase introduisant une liste, explique seulement le rôle "
        "collectif et l'appartenance explicitement indiqués ; ne déduis pas une définition "
        "individuelle, une syntaxe ou un comportement supplémentaire du nom d'un item. "
        "ne traduis pas un nom d'élément ou une instruction en balise ou commande absente. "
        "Place le code seul dans une section dédiée ou dans un bloc ``` ; "
        "sépare l'explication française du code. Ne change aucune valeur "
        "et n'invente pas un second exemple. "
        "Recopie un extrait continu, ponctuation comprise : n'ajoute aucun "
        "point-virgule, balise englobante, attribut, nom fictif ou paramètre "
        "générique. Ne reconstruis pas un programme complet à partir d'un fragment. "
        "Ne répare jamais le code du PDF et ne supprime pas un exemple requis pour contourner un rejet.\n\n"

        "LISIBILITÉ : une section = une idée principale. "
        "Utilise des phrases courtes. "
        "Garde les conditions et détails nécessaires à la compréhension. "
        "Lorsqu'une notion nécessite plusieurs idées, crée plusieurs "
        "petites sections plutôt qu'un seul bloc massif.\n\n"

        "Fais des fiches concises, directement révisables et sans "
        "répétitions. N'utilise pas de Markdown en gras avec **texte**.\n\n"

        'JSON strict : {"cards": [{"concept_id": "...", "sections": ['
        '{"title": "Définition", "content": "Reformulation fidèle", "source_ref": null}, '
        '{"title": "Exemple du cours", "content": "", "source_ref": "code-1"}'
        ']}]}. Ces sections illustrent le format, elles ne sont pas obligatoires. '
        'Pour la prose : source_ref null ou omis, jamais une chaîne vide. '
        'Pour le code : choisis un identifiant réellement présent dans le catalogue de la notion.\n\n'

        "NOTIONS ET PREUVES AUTORISÉES :\n"
        f"{requested}\n\n"

        "PAGES PHYSIQUES UTILISÉES PAR STUDYPILOT POUR LES "
        "VÉRIFICATIONS AUTOMATIQUES : "
        f"{page_text}.\n"

        "Le contenu intégral de ces pages ne t'est volontairement "
        "pas fourni : seules les PREUVES ci-dessus définissent "
        "ce que chaque fiche doit enseigner."
    )



def _split_concepts(
    concepts: list[Concept],
    *,
    batch_size: int = 4,
) -> list[list[Concept]]:
    """Découpe uniquement les appels IA, jamais le contenu pédagogique."""

    batches, batch, size = [], [], 0
    for concept in concepts:
        length = len(_concept_description(concept))
        if batch and (len(batch) >= batch_size or size + length > 14000):
            batches.append(batch)
            batch, size = [], 0
        batch.append(concept)
        size += length
    if batch:
        batches.append(batch)
    return batches


def _record_card_diagnostic(
    diagnostics: dict[str, list[str]] | None,
    concept_id: str,
    message: str,
) -> None:
    if diagnostics is None or not concept_id:
        return

    bucket = diagnostics.setdefault(concept_id, [])
    if message not in bucket:
        bucket.append(message)


def _validate_cards(
    raw_cards: object,
    expected: list[Concept],
    pages: list[dict],
    diagnostics: dict[str, list[str]] | None = None,
) -> dict[str, StudyCard]:
    if not isinstance(raw_cards, list):
        for concept in expected:
            _record_card_diagnostic(
                diagnostics,
                concept.concept_id,
                "réponse IA sans liste de fiches",
            )
        return {}

    expected_by_id = {
        concept.concept_id: concept
        for concept in expected
    }

    page_map = {
        int(page["page"]): page
        for page in pages
    }

    generated: dict[str, StudyCard] = {}
    seen_expected_ids: set[str] = set()

    for raw in raw_cards:
        if not isinstance(raw, dict):
            continue

        concept_id = str(
            raw.get("concept_id") or ""
        ).strip()

        if concept_id not in expected_by_id:
            continue

        seen_expected_ids.add(concept_id)

        if concept_id in generated:
            _record_card_diagnostic(
                diagnostics,
                concept_id,
                "fiche dupliquée dans la réponse IA",
            )
            continue

        concept = expected_by_id[concept_id]
        raw_sections = raw.get("sections")

        if not isinstance(raw_sections, list):
            _record_card_diagnostic(
                diagnostics,
                concept_id,
                "champ sections absent ou invalide",
            )
            continue

        sections: list[CardSection] = []
        used_keys: set[str] = set()
        content_invalid = False

        concept_pages = [
            page_map[page_number]
            for page_number in concept.source_pages
            if page_number in page_map
        ]

        if not concept_pages:
            _record_card_diagnostic(
                diagnostics,
                concept_id,
                "aucune page source validée disponible",
            )
            continue

        source_problem = proof_issue(concept, concept_pages)
        if source_problem:
            _record_card_diagnostic(diagnostics, concept_id, source_problem)
            continue

        for raw_section in raw_sections:
            if not isinstance(raw_section, dict):
                _record_card_diagnostic(
                    diagnostics,
                    concept_id,
                    "section JSON invalide",
                )
                continue

            title = re.sub(
                r"\s+",
                " ",
                str(raw_section.get("title") or ""),
            ).strip()

            content = str(
                raw_section.get("content") or ""
            ).strip()
            if raw_section.get("source_ref") is not None:
                snippet = source_code_snippets(concept).get(raw_section["source_ref"])
                if snippet is None:
                    _record_card_diagnostic(diagnostics, concept_id,
                        f"source_ref inconnu pour cette notion : {raw_section['source_ref']!r}. Choisis un identifiant de son propre catalogue.")
                    content_invalid = True
                    continue
                if content and not same_literal_code(content, snippet):
                    _record_card_diagnostic(diagnostics, concept_id,
                        "Avec source_ref, content doit être vide ou contenir exactement l'extrait sélectionné. Place la prose dans une autre section.")
                    content_invalid = True
                    continue
                content = "```\n" + snippet + "\n```"

            if content and not content.startswith("```"):
                exact = next((v for v in source_code_snippets(concept).values() if same_literal_code(content, v)), None)
                if exact is not None:
                    content = "```\n" + exact + "\n```"

            if not title or not content:
                _record_card_diagnostic(
                    diagnostics,
                    concept_id,
                    "section vide rejetée",
                )
                continue

            if _looks_mostly_english(
                f"{title}\n{content}"
            ):
                _record_card_diagnostic(
                    diagnostics,
                    concept_id,
                    (
                        f"section {title!r} rejetée : "
                        "prose majoritairement anglaise"
                    ),
                )
                continue

            if _section_is_too_dense(content):
                _record_card_diagnostic(
                    diagnostics,
                    concept_id,
                    (
                        f"section {title!r} rejetée : "
                        "contenu trop dense pour une fiche"
                    ),
                )
                continue

            code_problem = code_issue(content, concept)
            if code_problem:
                _record_card_diagnostic(diagnostics, concept_id, f"section {title!r} rejetée : {code_problem}")
                content_invalid = True
                continue

            if _contains_math(content):
                source_text = "\n".join(
                    _clean_card_evidence(item.excerpt)
                    for item in concept.evidence
                )
                supported, reason = _math_is_supported(content, source_text)
                if not supported:
                    content_invalid = True
                    _record_card_diagnostic(
                        diagnostics,
                        concept_id,
                        f"section {title!r} rejetée : {reason or 'notation absente des preuves'}",
                    )
                    continue

            base_key = _section_key(title)
            key = base_key
            suffix = 2

            while key in used_keys:
                key = f"{base_key}_{suffix}"
                suffix += 1

            used_keys.add(key)

            try:
                sections.append(
                    CardSection(
                        key=key,
                        title=title,
                        content=content,
                    )
                )
            except ValidationError as error:
                _record_card_diagnostic(
                    diagnostics,
                    concept_id,
                    (
                        f"section {title!r} rejetée par le schéma : "
                        f"{str(error).splitlines()[0]}"
                    ),
                )

        if content_invalid:
            continue

        if not sections:
            _record_card_diagnostic(
                diagnostics,
                concept_id,
                "aucune section valide après contrôle",
            )
            continue

        try:
            card = StudyCard(
                card_id=_card_id(concept_id),
                concept_id=concept_id,
                title=concept.title,
                concept_type=concept.type,
                primary_part_id=concept.primary_part_id,
                related_part_ids=list(
                    concept.related_part_ids
                ),
                sections=sections,
                source_pages=list(
                    concept.source_pages
                ),
            )
        except ValidationError as error:
            _record_card_diagnostic(
                diagnostics,
                concept_id,
                (
                    "fiche rejetée par le schéma : "
                    f"{str(error).splitlines()[0]}"
                ),
            )
            continue

        if issue := publication_issue(card):
            _record_card_diagnostic(diagnostics, concept_id, issue)
            continue
        generated[concept_id] = card

    for concept in expected:
        if (
            concept.concept_id not in generated
            and concept.concept_id not in seen_expected_ids
        ):
            _record_card_diagnostic(
                diagnostics,
                concept.concept_id,
                "CONCEPT_ID absent de la réponse IA",
            )

    return generated



def _generate_batch(
    part: dict,
    pages: list[dict],
    concepts: list[Concept],
    *,
    model: str,
) -> list[StudyCard]:
    """
    Génère toutes les fiches d'un lot.

    Les fiches valides sont conservées immédiatement.
    Seules les fiches manquantes ou invalides sont redemandées.
    """

    problems = [f"{c.title}: {issue}" for c in concepts
                if (issue := proof_issue(c, [p for p in pages if p["page"] in c.source_pages]))]
    if problems:
        raise ValueError(
            "Sources insuffisantes. " + " ; ".join(problems)
            + ". Reconstruis les parties concernées de l'inventaire après lecture OCR."
        )

    generated: dict[str, StudyCard] = {}

    remaining = list(concepts)
    visual_errors = {}

    # Une illustration attestée est reproduite depuis le PDF. Le modèle
    # textuel n'a ni à la redessiner ni à inventer son interprétation.
    for concept in concepts:
        if concept.illustrations and pages and pages[0].get("_source_pdf"):
            from src.courses.visual_cards import write_visual_card
            try:
                generated[concept.concept_id] = write_visual_card(concept,pages[0]["_source_pdf"],model=model,card_id=_card_id(concept.concept_id))
            except AIUsageLimitError:
                raise
            except Exception as error:
                visual_errors[concept.concept_id] = str(error)
            continue
        if concept.illustrations:
            generated[concept.concept_id] = StudyCard(
                card_id=_card_id(concept.concept_id), concept_id=concept.concept_id,
                title=concept.title, concept_type=concept.type,
                primary_part_id=concept.primary_part_id, related_part_ids=concept.related_part_ids,
                source_pages=concept.source_pages, illustrations=concept.illustrations,
                sections=[CardSection(key="illustration", title="Extrait du cours" if concept.learning_points else "Illustration du cours",
                                      content="Le passage original est conservé ci-dessous pour respecter sa mise en page et ses notations."
                                      if concept.learning_points else "Observe l’illustration originale ci-dessous.")],
            )
    remaining = [c for c in remaining if c.concept_id not in generated and c.concept_id not in visual_errors]
    if not remaining and not visual_errors:
        return list(generated.values())

    # Une preuve uniquement composée de code n'a pas à être réécrite par le
    # générateur. Construire la citation exacte, puis conserver le même audit.
    literal_raw = []
    for concept in remaining:
        if concept.learning_points:
            continue
        if len(concept.evidence) != 1:
            continue
        literal = concept.evidence[0].excerpt.strip()
        match = next((key for key, value in source_code_snippets(concept).items() if value == literal), None)
        if match:
            literal_raw.append({"concept_id": concept.concept_id, "sections": [
                {"title": "Exemple du cours", "source_ref": match, "content": ""}
            ]})
    if literal_raw:
        candidates = _validate_cards(literal_raw, concepts, pages)
        try:
            verdicts = audit_cards(candidates, concepts, model=model)
            generated.update({key: card for key, card in candidates.items() if not verdicts.get(key)})
            remaining = [c for c in concepts if c.concept_id not in generated and c.concept_id not in visual_errors]
        except AIUsageLimitError:
            raise
        except Exception:
            # Les tentatives ordinaires produiront un diagnostic détaillé.
            pass

    attempts = [
    {
        "temperature": 0.05,
        "num_predict": 2200,
        "num_ctx": 8192,
        "repeat_penalty": 1.08,
        "repeat_last_n": 128,
        "top_p": 0.90,
    },
    {
        "temperature": 0.15,
        "num_predict": 2200,
        "num_ctx": 8192,
        "repeat_penalty": 1.15,
        "repeat_last_n": 256,
        "top_p": 0.90,
    },
   ] 

    last_error: Exception | None = None
    diagnostics: dict[str, list[str]] = {k:[v] for k,v in visual_errors.items()}

    # Première phase :
    # on réessaie uniquement les fiches encore manquantes.
    for attempt_index, options in enumerate(
        attempts,
        start=1,
    ):
        if not remaining:
            break

        prompt = _cards_prompt(
            part,
            pages,
            remaining,
        )

        if attempt_index > 1:
            prompt += (
                "\n\nATTENTION : certaines fiches demandées "
                "n'ont pas été produites correctement lors de "
                "la tentative précédente. "
                "Génère exactement une fiche pour CHAQUE "
                "CONCEPT_ID ci-dessus. "
                "Chaque section doit avoir un titre et soit un contenu non vide, "
                "soit un source_ref valide avec content vide."
            )
            prompt += "\nMOTIFS DES REJETS :\n" + "\n".join(
                f"- {c.title}: " + " | ".join(diagnostics.get(c.concept_id, [])[-3:])
                for c in remaining
            )

        try:
            data = chat_json(
                response_model=_AICardBatch,
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                     "Tu génères des fiches pédagogiques StudyPilot. "
                     "Le PDF et les preuves fournies sont les seules sources autorisées. "
                     "Réponds uniquement en JSON valide. "
                     "N'ajoute aucune connaissance extérieure. "
                     "Toute la prose pédagogique doit être en français. "
                            "Le code, la syntaxe et les notations techniques restent inchangés. "
                            "Respecte exactement les notations mathématiques du cours. "
                            "Reste concis, aéré et évite toute répétition."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                options=options,
            )

            valid = _validate_cards(
                data.get("cards"),
                remaining,
                pages,
                diagnostics,
            )

            verdicts = audit_cards(valid, remaining, model=model)
            for identifier, issues in verdicts.items():
                if issues:
                    _record_card_diagnostic(diagnostics, identifier, "contenu sans preuve : " + " | ".join(issues))
                    del valid[identifier]

            generated.update(valid)

            remaining = [
                concept
                for concept in remaining
                if concept.concept_id not in generated
            ]

        except AIUsageLimitError:
            raise
        except Exception as error:
            last_error = error
            for concept in remaining:
                _record_card_diagnostic(diagnostics, concept.concept_id,
                    f"Réponse à corriger : {type(error).__name__}: {str(error)[:1500]}")

    # Deuxième phase :
    # les rares fiches encore manquantes sont générées
    # individuellement pour éviter qu'un gros lot les fasse disparaître.
    for concept in list(remaining):
        prompt = _cards_prompt(
            part,
            pages,
            [concept],
        )

        prompt += (
            "\n\nTu dois maintenant générer UNE SEULE fiche. "
            f"Le seul CONCEPT_ID attendu est : "
            f"{concept.concept_id}. "
            "Produis une fiche complète couvrant tous les points demandés. "
            "Chaque section a un titre et soit du contenu, soit un source_ref avec content vide. "
            "N'écris aucun code librement : utilise uniquement un source_ref du catalogue. "
            "Si le catalogue est vide, restitue les explications et formules attestées en prose ou LaTeX, avec source_ref null ; n'invente aucune syntaxe de programmation."
        )
        concept_generated = False

        for options in attempts:
            retry_prompt = prompt + (
                "\nMOTIFS DES REJETS (ce sont des erreurs à éviter, pas des sources) :\n"
                + " | ".join(diagnostics.get(concept.concept_id, [])[-3:])
                + "\nPour corriger un rejet de code, repars uniquement des PREUVES. "
                "Recopie exactement le fragment autorisé ; conserve les exemples requis. "
                "N'ajoute rien pour rendre un fragment exécutable."
            )
            try:
                data = chat_json(
                    response_model=_AICardBatch,
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Tu génères une seule fiche pédagogique StudyPilot. "
                                "Le PDF et les preuves fournies sont les seules sources autorisées. "
                                "Réponds uniquement en JSON valide. "
                                "N'ajoute aucune connaissance extérieure. "
                                "Toute la prose pédagogique doit être en français. "
                                "Le code, la syntaxe et les notations techniques restent inchangés. "
                                "Respecte exactement les notations du cours."
                            ),
                        },
                        {
                            "role": "user",
                            "content": retry_prompt,
                        },
                    ],
                    options=options,
                )

                valid = _validate_cards(
                    data.get("cards"),
                    [concept],
                    pages,
                    diagnostics,
                )

                verdicts = audit_cards(valid, [concept], model=model)
                for identifier, issues in verdicts.items():
                    if issues:
                        _record_card_diagnostic(diagnostics, identifier, "contenu sans preuve : " + " | ".join(issues))
                        del valid[identifier]

                card = valid.get(
                    concept.concept_id
                )

                if card is not None:
                    generated[
                        concept.concept_id
                    ] = card

                    concept_generated = True
                    break

            except AIUsageLimitError:
                raise
            except Exception as error:
                last_error = error
                _record_card_diagnostic(diagnostics, concept.concept_id,
                    f"Réponse à corriger : {type(error).__name__}: {str(error)[:1500]}")

        if not concept_generated:
            continue

    missing = [
        concept
        for concept in concepts
        if concept.concept_id not in generated
    ]

    if missing:
        details: list[str] = []

        for concept in missing:
            reasons = diagnostics.get(concept.concept_id) or []
            if reasons:
                details.append(
                    f"{concept.title}: "
                    + " | ".join(reasons[-3:])
                )
            else:
                details.append(
                    f"{concept.title}: aucun diagnostic détaillé"
                )

        message = (
            "Fiches encore impossibles à générer. "
            + " ; ".join(details)
        )

        if last_error is not None:
            message += (
                f" ; dernière erreur IA : "
                f"{type(last_error).__name__}: "
                f"{str(last_error)[:300]}"
            )

        raise CardGenerationError(message, generated.values(), {
            c.concept_id: " | ".join(diagnostics.get(c.concept_id, [])[-3:])
            or (f"{type(last_error).__name__}: {last_error}" if last_error else "Réponse IA manquante")
            for c in missing
        })

    return [
        generated[concept.concept_id]
        for concept in concepts
    ]


def preview_card(
    course_id: str,
    concept_index: int | None = None,
    *,
    concept_title: str | None = None,
    model: str = STUDY_MODEL,
) -> tuple[Concept, StudyCard]:
    """Génère une seule fiche pour diagnostic, sans rien sauvegarder."""

    if (concept_index is None) == (concept_title is None):
        raise ValueError("Choisis --index ou --title pour identifier une notion.")
    if concept_index is not None and concept_index < 1:
        raise ValueError("--index doit être supérieur ou égal à 1.")

    course = load_course(course_id)
    plan = load_course_plan(course)

    if plan is None:
        raise ValueError("Le cours ne possède pas de plan valide.")

    repository = CourseRepository()

    try:
        inventory = ConceptInventory.model_validate(
            repository.load_inventory(course_id)
        )
    except (StorageError, ValidationError) as error:
        raise ValueError(
            "Le cours ne possède pas d'inventaire valide."
        ) from error

    if any(part.status == "error" for part in inventory.parts):
        raise ValueError(
            "L'inventaire contient encore des parties en erreur."
        )

    if not inventory.concepts:
        raise ValueError("L'inventaire ne contient aucune notion.")

    if concept_index is not None and concept_index > len(inventory.concepts):
        raise ValueError(
            f"--index doit être compris entre 1 et {len(inventory.concepts)}."
        )

    if concept_title is not None:
        query = concept_title.strip().casefold()
        if not query:
            raise ValueError("--title ne doit pas être vide.")
        matches = [c for c in inventory.concepts if c.title.casefold() == query]
        if not matches:
            matches = [c for c in inventory.concepts if query in c.title.casefold()]
        if len(matches) != 1:
            raise ValueError(
                f"Le titre {concept_title!r} correspond à {len(matches)} notions. "
                "Utilise 'inventory list' et --index pour choisir."
            )
        concept = matches[0]
    else:
        concept = inventory.concepts[concept_index - 1]

    part = next(
        (
            item
            for item in plan["parts"]
            if str(item["id"]) == concept.primary_part_id
        ),
        None,
    )

    if part is None:
        raise ValueError(
            "La partie principale de cette notion n'existe plus dans le plan."
        )

    pdf_path = COURSE_PDF_DIR / course["source_filename"]
    document = extract_document(pdf_path)
    for source_page in document["pages"]:source_page["_source_pdf"] = str(pdf_path)

    if document["file_hash"] != course["file_hash"]:
        raise ValueError("Le PDF actuel ne correspond plus au cours.")

    material = prepare_material(inventory, document, plan, repository, model=model)
    relation = next((r for r in material.relations if r['concept_id'] == concept.concept_id), None)
    wanted = relation['target_id'] if relation else concept.concept_id
    prepared = next((c for c in material.inventory.concepts if c.concept_id == wanted), None)
    if prepared is None or any(issue_blocks_concept(i, prepared) for i in material.issues):
        reasons = ' ; '.join(i['reason'] for i in material.issues if prepared is None or issue_blocks_concept(i, prepared))
        raise ValueError('Revue pédagogique à reprendre : ' + reasons)
    concept = prepared
    part = next(item for item in plan['parts'] if str(item['id']) == concept.primary_part_id)
    if concept.relevance == "mention_only":
        raise ValueError("Simple mention écartée des fiches : " + (concept.relevance_reason or concept.title))

    pages = _concept_pages(
        document,
        [concept],
    )

    if not pages:
        raise ValueError(
            "Aucune page source disponible pour cette notion."
        )

    cards = _generate_batch(
        part,
        pages,
        [concept],
        model=model,
    )

    if issue := publication_issue(cards[0]):
        raise ValueError(issue)
    cards[0].covered_concept_ids = [r['concept_id'] for r in material.relations if r['target_id'] == concept.concept_id]
    return concept, cards[0]


def _save_cards(
    repository: CourseRepository,
    collection: CardCollection,
) -> None:
    repository.save_cards(
        collection.course_id,
        collection.model_dump(mode="json"),
    )


def build_cards(course_id, *, model=STUDY_MODEL, force=False, progress_callback=None):
    import os
    import tempfile
    repository = CourseRepository()
    path = repository.paths(course_id).cards
    original = path.read_bytes() if path.is_file() else None
    try:
        return _build_cards(course_id, model=model, force=force, progress_callback=progress_callback)
    except AIUsageLimitError:
        if original is not None and path.is_file() and path.read_bytes() != original:
            backup(path, 'interrupted_quota')
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
                handle.write(original)
                temporary = handle.name
            try:
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        raise


def _build_cards(
    course_id: str,
    *,
    model: str = STUDY_MODEL,
    force: bool = False,
    progress_callback=None,
) -> CardCollection:
    """Construit ou reprend les fiches d'un cours."""

    course = load_course(course_id)
    plan = load_course_plan(course)

    if plan is None:
        raise ValueError(
            "Le cours ne possède pas de plan valide."
        )

    repository = CourseRepository()

    try:
        inventory = ConceptInventory.model_validate(
            repository.load_inventory(course_id)
        )
    except (StorageError, ValidationError) as error:
        raise ValueError(
            "Le cours ne possède pas d'inventaire valide."
        ) from error

    error_parts = [
        part
        for part in inventory.parts
        if part.status == "error"
    ]

    if error_parts:
        raise ValueError(
            "L'inventaire contient encore des parties en erreur."
        )

    expected_part_ids = {
        str(part["id"])
        for part in plan["parts"]
    }

    complete_inventory_ids = {
        part.part_id
        for part in inventory.parts
        if part.status == "complete"
    }

    if expected_part_ids != complete_inventory_ids:
        raise ValueError(
            "L'inventaire n'est pas complet pour toutes les parties."
        )

    current_inventory_hash = _inventory_hash(
        inventory
    )
    if inventory.file_hash != course["file_hash"]:
        raise ValueError("L'inventaire ne correspond plus au PDF du cours.")

    pdf_path = (
        COURSE_PDF_DIR
        / course["source_filename"]
    )

    document = extract_document(pdf_path)
    for source_page in document["pages"]:source_page["_source_pdf"] = str(pdf_path)

    if document["file_hash"] != course["file_hash"]:
        raise ValueError(
            "Le PDF actuel ne correspond plus au cours."
        )

    material = prepare_material(inventory, document, plan, repository, model=model, progress_callback=progress_callback)
    inventory = material.inventory
    current_inventory_hash = _inventory_hash(inventory)
    review_issues = material.issues
    relations = material.relations
    try:
        previous = CardCollection.model_validate(repository.load_cards(course_id))
    except (StorageError, ValidationError):
        previous = None
    drafts = list({c.concept_id: c for c in ((previous.archived_cards + previous.unreviewed_cards + previous.cards) if previous else [])}.values())
    stable_card_ids = {c.concept_id: c.card_id for c in drafts}
    for relation in relations:
        relation['source_card_id'] = stable_card_ids.get(relation['concept_id'])
        relation['target_card_id'] = stable_card_ids.get(relation['target_id'], _card_id(relation['target_id']))
    backup(repository.paths(course_id).cards, 'before_quality_v14')
    cards: list[StudyCard] = []
    coverage: list[CardPartCoverage] = []
    blocked = []
    ignored = []
    for concept in inventory.concepts:
        if concept.relevance == "mention_only":
            ignored.append(BlockedCard(concept_id=concept.concept_id, title=concept.title,
                primary_part_id=concept.primary_part_id, source_pages=concept.source_pages,
                status="mention_only", reason=concept.relevance_reason or "Simple mention sans développement."))
            continue
        source_pages = _concept_pages(document, [concept])
        if any(issue_blocks_concept(i, concept) for i in review_issues):
            continue
        issue = proof_issue(concept, source_pages) if source_pages else "Aucune page source disponible."
        if issue and (concept.evidence_issue or "").startswith("Vérification de pertinence à reprendre"):
            issue = concept.evidence_issue
        if issue:
            blocked.append(BlockedCard(
                concept_id=concept.concept_id, title=concept.title,
                primary_part_id=concept.primary_part_id,
                source_pages=concept.source_pages, reason=issue,
            ))
    blocked_ids = {item.concept_id for item in blocked + ignored}
    blocked_ids.update(c.concept_id for c in inventory.concepts if any(issue_blocks_concept(i, c) for i in review_issues))
    concept_hashes = {
        c.concept_id: _concept_hash(c)
        for c in inventory.concepts
    }

    if not force:
        try:
            saved = CardCollection.model_validate(
                repository.load_cards(course_id)
            )
        except (StorageError, ValidationError):
            saved = None

        if (
        saved is not None
        and saved.file_hash == course["file_hash"]
        and saved.model == model
        and saved.schema_version >= 1
        ):
            current = {c.concept_id: c for c in inventory.concepts}
            recheck = []
            for card in drafts:
                if card.concept_id not in current or card.concept_id in blocked_ids or publication_issue(card):
                    continue
                if (saved.quality_version == QUALITY_VERSION
                        and saved.concept_hashes.get(card.concept_id) == concept_hashes[card.concept_id]):
                    cards.append(card)
                elif current[card.concept_id].card_role != "visual":
                    recheck.append(current[card.concept_id])
            # Migration des caches antérieurs et preuves modifiées : vérifier
            # les fiches existantes avant de demander une nouvelle génération.
            old_cards = {card.concept_id: card for card in drafts}
            for batch in _split_concepts(recheck):
                raw = [{"concept_id": c.concept_id, "sections": [
                    {"title": s.title, "content": s.content} for s in old_cards[c.concept_id].sections
                ]} for c in batch]
                valid = _validate_cards(raw, batch, _concept_pages(document, batch))
                try:
                    verdicts = audit_cards(valid, batch, model=model)
                    cards.extend(card for key, card in valid.items() if not verdicts.get(key) and not publication_issue(card))
                except AIUsageLimitError:
                    raise
                except Exception:
                    pass  # Ces notions restent à générer avec un diagnostic normal.

    # Une partie en erreur peut déjà contenir des fiches validées.
    ready_ids = {card.concept_id for card in cards}
    failures = []
    total = len(plan["parts"])
    coverage = [CardPartCoverage(part_id=str(p['id']), part_number=str(p['number']),
                    status='partial', cards_generated=sum(c.primary_part_id == str(p['id']) for c in cards),
                    message='Traitement à terminer ; reprise possible.') for p in plan['parts']]
    completed_states = {}

    def refresh_related_coverage():
        for state in coverage:
            if state.part_id not in completed_states:
                continue
            state.status, state.message = completed_states[state.part_id]
            pending_links = [r for r in relations if r.get('primary_part_id') == state.part_id
                             and r['target_id'] not in ready_ids]
            if pending_links and state.status == 'complete':
                state.status = 'partial'
                state.message = f'{len(pending_links)} contenu(s) regroupé(s) en attente de leur fiche cible.'

    def preserved_drafts():
        ready = {c.concept_id for c in cards}
        retired = {i.concept_id for i in ignored} | {r['concept_id'] for r in relations if r['target_id'] in ready}
        return dict(
            unreviewed_cards=[c for c in drafts if c.concept_id not in ready | retired],
            archived_cards=[c for c in drafts if c.concept_id in retired and c.concept_id not in ready],
        )

    def checkpoint():
        refresh_related_coverage()
        for card in cards:
            card.card_id = stable_card_ids.get(card.concept_id, card.card_id)
            card.covered_concept_ids = [r['concept_id'] for r in relations if r['target_id'] == card.concept_id]
        _save_cards(repository, CardCollection(
            course_id=course_id, file_hash=course["file_hash"],
            inventory_hash=current_inventory_hash, model=model,
            parts=coverage, cards=cards, blocked=blocked, failures=failures, ignored=ignored, concept_hashes=concept_hashes,
            quality_version=QUALITY_VERSION, quality_hash=material.quality_hash, review_issues=review_issues, relations=relations,
            **preserved_drafts(),
        ))

    checkpoint()
    for position, part in enumerate(plan["parts"], start=1):
        part_id = str(part["id"])
        pending = [c for c in inventory.concepts
                   if c.primary_part_id == part_id
                   and c.concept_id not in blocked_ids | ready_ids]
        part_blocked = [item for item in blocked if item.primary_part_id == part_id]
        state = coverage[position - 1]
        state.status = 'error'
        state.message = 'Génération en cours ; reprise possible.'
        for batch in _split_concepts(pending):
            batch_pages = _concept_pages(document, batch)
            errors = {}
            try:
                generated = _generate_batch(part, batch_pages, batch, model=model)
            except CardGenerationError as error:
                generated, errors = error.generated, error.failures
            except AIUsageLimitError:
                raise
            except Exception as error:
                generated = []
                errors = {c.concept_id: f"{type(error).__name__}: {error}" for c in batch}
            for card in generated:
                if issue := publication_issue(card):
                    errors[card.concept_id] = issue
                    continue
                if card.concept_id not in ready_ids:
                    card.covered_concept_ids = [r["concept_id"] for r in relations if r["target_id"] == card.concept_id]
                    cards.append(card)
                    ready_ids.add(card.concept_id)
            for concept in batch:
                if concept.concept_id not in ready_ids:
                    failures.append(BlockedCard(
                        concept_id=concept.concept_id, title=concept.title,
                        primary_part_id=part_id, source_pages=concept.source_pages,
                        status="card_incomplete" if "incomplet" in errors.get(concept.concept_id, "").lower() else "generation_error",
                        reason=errors.get(concept.concept_id, "Fiche absente de la réponse IA."),
                    ))
            state.cards_generated = sum(c.primary_part_id == part_id for c in cards)
            checkpoint()
            if progress_callback:
                progress_callback(position, total, str(part["number"]),
                                  f"{state.cards_generated} fiches sauvegardées")
        part_failures = [item for item in failures if item.primary_part_id == part_id]
        state.cards_generated = sum(c.primary_part_id == part_id for c in cards)
        state.status = "error" if part_failures else ("partial" if part_blocked else "complete")
        part_reviews = [i for i in review_issues if issue_affects_part(i, part_id)]
        if part_reviews and state.status == "complete":
            state.status = "partial"
        state.message = (
            f"{len(part_failures)} échec(s) de génération ; {len(part_blocked)} source(s) insuffisante(s)."
            if part_failures or part_blocked else ("Revue pédagogique / couverture à reprendre." if part_reviews else None)
        )
        completed_states[part_id] = (state.status, state.message)
        checkpoint()
        if progress_callback:
            progress_callback(position, total, str(part["number"]), "cached" if not pending and state.status == "complete" else state.status)

    refresh_related_coverage()
    final = CardCollection(
        course_id=course_id,
        file_hash=course["file_hash"],
        inventory_hash=current_inventory_hash,
        model=model,
        parts=coverage,
        cards=cards,
        blocked=blocked,
        failures=failures,
        ignored=ignored,
        concept_hashes=concept_hashes,
        quality_version=QUALITY_VERSION, quality_hash=material.quality_hash,
        review_issues=review_issues, relations=relations,
        **preserved_drafts(),
    )

    _save_cards(
        repository,
        final,
    )

    return final


def cards_summary(
    collection: CardCollection,
) -> dict[str, int]:
    collection = publication_view(collection)
    complete = sum(
        part.status == "complete"
        for part in collection.parts
    )

    errors = sum(
        part.status == "error"
        for part in collection.parts
    )

    insufficient = {item.concept_id for item in collection.blocked if item.status == 'source_insufficient'}
    insufficient.update(i['concept_id'] for i in collection.review_issues
                        if i.get('status') == 'source_insufficient' and i.get('concept_id'))
    return {
        "cards": len(collection.cards),
        "review_issues": len(collection.review_issues),
        "insufficient_sources": len(insufficient),
        "grouped_concepts": len(collection.relations),
        "complete_parts": complete,
        "error_parts": errors,
        "partial_parts": sum(part.status == "partial" for part in collection.parts),
        "blocked_concepts": len(collection.blocked),
        "failed_concepts": len(collection.failures),
        "ignored_concepts": len(collection.ignored),
        "archived_cards": len(collection.archived_cards),
        "parts": len(collection.parts),
    }
