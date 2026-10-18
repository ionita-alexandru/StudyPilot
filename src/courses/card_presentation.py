"""Rendu sûr des fiches ; la pertinence reste contrôlée à partir du PDF.

Un extrait de syntaxe, une formule ou un schéma peut être utile sans prose.
Ce module ne prétend pas établir une preuve sémantique à partir du style.
"""
import re
import unicodedata
from html import escape

MATH = r"\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$|(?<!\\)\$[^$\n]+(?<!\\)\$"
INLINE = re.compile(r"`[^`\n]+`|" + MATH + r"|\*\*[^*\n]+\*\*|(?<!\*)\*[^*\n]+\*(?!\*)")
BLOCK = re.compile(r"```[\s\S]*?(?:```|$)|\\\[[\s\S]*?\\\]|\$\$[\s\S]*?\$\$")


def normal(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _data(card):
    return card if isinstance(card, dict) else card.model_dump(mode="json")


def prose(text):
    text = re.sub(r"```[\s\S]*?(?:```|$)", "", text)
    return re.sub(MATH, "", text).strip()


def useful(text, title=""):
    """Choisit une prose à mettre en avant, sans décider de publier la fiche."""
    text = prose(text)
    if not text or normal(text) == normal(title):
        return False
    if re.fullmatch(r"[\w-]+\s*:[\s\S]+", text) or any(c in text for c in "{};"):
        return False
    if all(re.match(r"^\s*(?:[-*•]|\d+[.)])\s+", line) for line in text.splitlines()):
        return False
    return len(re.findall(r"[^\W\d_]+", text, re.UNICODE)) >= 2


def publication_issue(card):
    """Rejette seulement le contenu vide ou répétant son titre.

    Ni la langue, ni le nombre de mots, ni les virgules ne permettent de
    déterminer si le PDF développe une notion. Inventaire et audits s'en chargent.
    """
    data = _data(card)
    if isinstance(data,dict) and data.get('sections') and all(s.get('content','').startswith('Le passage original est conservé ci-dessous') for s in data['sections']):
        return 'Extrait PDF sans fiche rédigée : transcription et audit visuel à reprendre.'
    if data.get("illustrations"):
        return None
    title = normal(data.get("title", ""))
    for section in data.get("sections", []):
        content = section.get("content", "").strip()
        cleaned = re.sub(r"```(?:[a-zA-Z0-9_+-]*\n)?|```", "", content).strip()
        if re.search(r"\w", cleaned, re.UNICODE) and normal(cleaned) != title:
            return None
    return "Fiche sans contenu distinct de son titre : génération à reprendre."


def publication_view(collection):
    """Vue cohérente des caches, sans modifier ni enregistrer l'original."""
    from src.models.card import BlockedCard
    view = collection.model_copy(deep=True)
    valid = []
    failures = {item.concept_id: item for item in view.failures}
    from src.courses.pedagogy import QUALITY_VERSION, issue_affects_part
    legacy = view.quality_version != QUALITY_VERSION
    if legacy:
        for card in view.cards:
            failures[card.concept_id] = BlockedCard(concept_id=card.concept_id, title=card.title,
                primary_part_id=card.primary_part_id, source_pages=card.source_pages,
                status='review_pending', reason='Fiche ancienne à revalider avec les contrôles pédagogiques actuels.')
    invalid_parts = set()
    for card in view.cards:
        if legacy or (issue := publication_issue(card)):
            issue = "Fiche ancienne à revalider avec les contrôles pédagogiques actuels." if legacy else issue
            invalid_parts.add(card.primary_part_id)
            failures[card.concept_id] = BlockedCard(
                concept_id=card.concept_id, title=card.title,
                primary_part_id=card.primary_part_id, source_pages=card.source_pages,
                status="review_pending" if legacy else "card_incomplete", reason=issue)
        else:
            valid.append(card)
    view.cards = valid
    view.failures = list(failures.values())
    for part in view.parts:
        if part.part_id in invalid_parts:
            part.cards_generated = sum(c.primary_part_id == part.part_id for c in valid)
            part.status = "partial" if legacy else "error"
            part.message = "Revue pédagogique à reprendre." if legacy else "Fiche(s) sans contenu distinct du titre ; génération à reprendre."
    if view.review_issues:
        for part in view.parts:
            if part.status == 'complete' and any(issue_affects_part(i, part.part_id) for i in view.review_issues):
                part.status = 'partial'
                part.message = 'Couverture / revue pédagogique à reprendre.'
    return view


def _inline(text):
    result, offset = [], 0
    for match in INLINE.finditer(text):
        result.append(escape(text[offset:match.start()]))
        token = match.group()
        if token.startswith('`'):
            result.append('<code>' + escape(token[1:-1]) + '</code>')
        elif token.startswith('**'):
            result.append('<strong>' + escape(token[2:-2]) + '</strong>')
        elif token.startswith('*'):
            result.append('<em>' + escape(token[1:-1]) + '</em>')
        else:
            result.append(escape(token))  # Mathématiques conservées avant Markdown.
        offset = match.end()
    result.append(escape(text[offset:]))
    return ''.join(result)


def _paragraphs(text):
    result = []
    for paragraph in re.split(r"\n\s*\n", text.strip()):
        if not paragraph:
            continue
        lines = paragraph.splitlines()
        # Gère aussi les listes après une ligne d'introduction.
        pending, items, list_kind = [], [], None
        def flush_prose():
            if pending:
                result.append('<p>' + '<br>'.join(_inline(s) for s in pending) + '</p>')
                pending.clear()
        def flush_list():
            if items:
                result.append('<' + list_kind + '>' + ''.join('<li>' + _inline(s) + '</li>' for s in items) + '</' + list_kind + '>')
                items.clear()
        for line in lines:
            if re.fullmatch(r'\s*(?:\*{3,}|-{3,}|_{3,})\s*', line):
                flush_prose()
                flush_list()
                result.append('<hr>')
                continue
            heading = re.match(r'^#{1,4}\s+(.+)$', line)
            if heading:
                flush_prose()
                flush_list()
                result.append('<h3>' + _inline(heading[1]) + '</h3>')
                continue
            match = re.match(r"^\s*([-*•]|\d+[.)])\s+(.+)$", line)
            if match:
                flush_prose()
                kind = 'ol' if match[1][0].isdigit() else 'ul'
                if items and kind != list_kind:
                    flush_list()
                list_kind = kind
                items.append(match[2])
            else:
                flush_list()
                pending.append(line)
        flush_prose()
        flush_list()
    return ''.join(result)


def render_text(text):
    """HTML source échappé ; code et formules isolés avant tout formatage."""
    # Certaines réponses JSON anciennes ont conservé un double échappement.
    # Les lignes de matrices et le code conservent leurs antislashs.
    def normalize_math(part):
        part=re.sub(r'\\\\([()\[\]])',r'\\\1',part)
        return re.sub(r'\\\\(?=(?:frac|dfrac|tfrac|sum|prod|int|bigcup|sqrt|lambda|alpha|beta|gamma|theta|pi|infty|left|right|begin|end|mathbb|mathbf|mathrm|operatorname)\b)',r'\\',part)
    text=''.join(piece if piece.startswith('```') else normalize_math(piece) for piece in re.split(r'(```[\s\S]*?(?:```|$))',text))
    result, offset = [], 0
    for match in BLOCK.finditer(text):
        result.append(_paragraphs(text[offset:match.start()]))
        block = match.group()
        if block.startswith('```'):
            body = block[3:]
            if body.endswith('```'):
                body = body[:-3]
            if '\n' in body:
                first, rest = body.split('\n', 1)
                if re.fullmatch(r'[a-zA-Z0-9_+-]*', first.strip()):
                    body = rest
            result.append('<pre><code>' + escape(body.strip('\n')) + '</code></pre>')
        else:
            result.append('<div class="sp-formula">' + escape(block) + '</div>')
        offset = match.end()
    result.append(_paragraphs(text[offset:]))
    return ''.join(result)


def present_card(card):
    data = _data(card)
    sections = data.get('sections', [])
    # Conserve le titre pédagogique : une définition ne devient pas une conclusion.
    preferred = {'à retenir', 'a retenir', 'définition', 'definition', 'principe', 'signification', 'explication'}
    lead = next((s for s in sections if normal(s['title']) in preferred and useful(s['content'], data['title'])), None)
    html = []
    for section in sections:
        cls = 'sp-takeaway' if section is lead else 'sp-card-section'
        title = '' if normal(section['title']) == normal(data['title']) else '<h3>' + escape(section['title']) + '</h3>'
        content = section['content']
        # Les anciens exemples fidèles peuvent être conservés après audit.
        # Leur absence de balises Markdown n'impose pas un rendu en paragraphe.
        if ('```' not in content and not re.search(MATH, content)
                and data.get('concept_type') not in {'formula', 'theorem'}):
            from src.courses.pedagogy import code_only
            if code_only({'quote': content}):
                content = '```\n' + content + '\n```'
        html.append('<section class="' + cls + '">' + title + render_text(content) + '</section>')
    title = data['title']
    title_html = _inline(title)
    # Mettre en relief les identifiants effectivement employés dans du code.
    candidates = re.findall(r'[A-Za-z_][\w.-]*|</?[A-Za-z][^>]*>', title)
    body = '\n'.join(s['content'] for s in sections)
    identifiers = [name for name in candidates if re.search(r'(?<![\w-])' + re.escape(name) + r'\s*[:=(]', body)
                   or ('-' in name and name in body)]
    if identifiers and '`' not in title:
        pattern = re.compile('|'.join(re.escape(name) for name in sorted(identifiers, key=len, reverse=True)))
        parts, offset = [], 0
        for match in pattern.finditer(title):
            parts.extend([escape(title[offset:match.start()]), '<code>' + escape(match.group()) + '</code>'])
            offset = match.end()
        title_html = ''.join(parts) + escape(title[offset:])
    return {**data, 'content_html': ''.join(html), 'title_html': title_html}
