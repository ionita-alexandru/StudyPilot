"""Un guide publié : noyaux courts et ressources, tous liés à leurs sources."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.courses.card_presentation import present_card, render_text, prose, normal, MATH
from src.storage.repository import read_json, write_json_atomic, StorageError

VERSION = 1


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def plan_version(plan):
    return digest([(p['id'], p['number'], p['title'], p['page_start'], p['page_end']) for p in plan['parts']])


class Symbol(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=60)
    meaning: str = Field(min_length=2,max_length=200)


class Entry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=2, max_length=150)
    role: Literal['core', 'example', 'exercise', 'detail', 'reference', 'orientation']
    kind: Literal['definition', 'concept', 'rule', 'property', 'theorem', 'formula', 'method', 'syntax'] = 'concept'
    objective: str = Field(min_length=5, max_length=300)
    body: str = Field(min_length=10, max_length=2400)
    source_ids: list[str] = Field(min_length=1)
    targets: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list, max_length=6)
    symbols: list[Symbol] = Field(default_factory=list, max_length=12)
    conditions: str = Field(default='', max_length=450)


    @model_validator(mode='before')
    @classmethod
    def normalize_metadata(cls, value):
        # Une comparaison est un concept ; targets décrit les ressources seulement.
        # Cette normalisation ne modifie ni le texte ni les preuves à auditer.
        if isinstance(value, dict):
            value = dict(value)
            if value.get('kind') == 'distinction':
                value['kind'] = 'concept'
            if value.get('role') == 'core':
                value['targets'] = []
        return value


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: str
    entry_keys: list[str]
    reason: str = Field(min_length=5, max_length=400)


class Draft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    entries: list[Entry]
    coverage: list[Selection]


def validate_draft(draft, sources, existing=()):
    """Contrôles locaux : destinations complètes, références, taille, pas de cycle."""
    draft = Draft.model_validate(draft)
    keys = {e.key for e in draft.entries}
    if len(keys) != len(draft.entries):
        raise ValueError('Identifiant de notion répété.')
    known = {s['id'] for s in sources}
    titles = {e.key: e.title for e in draft.entries if e.role == 'core'}
    roots = {e.key for e in draft.entries if e.role == 'core'} | set(existing)
    for entry in draft.entries:
        entry.prerequisites = [titles.get(name, name) for name in entry.prerequisites]
        # Du texte seul dans un conteneur mathématique n'est pas une formule.
        # Préserver les vraies expressions et rendre les identifiants en code.
        entry.body = re.sub(r'\\\(\s*\\text\{([A-Za-z_][\w.-]*)\}\s*\\\)', r'`\1`', entry.body)
        if not set(entry.source_ids) <= known or len(set(entry.source_ids)) != len(entry.source_ids):
            raise ValueError('Référence source inconnue ou répétée : ' + entry.key)
        if not set(entry.targets) <= roots or entry.key in entry.targets:
            raise ValueError('Destination de ressource inconnue ou cyclique.')
        if entry.role == 'core':
            if len(prose(entry.body).split()) > 110 or len(entry.body) > 1600:
                raise ValueError('Noyau trop long : garder idée, règle et conditions ; déplacer les développements.')
        if entry.body.count('```') % 2:
            raise ValueError('Bloc de code non fermé.')
        for opening, closing in [(r'\[', r'\]'), (r'\(', r'\)')]:
            if entry.body.count(opening) != entry.body.count(closing):
                raise ValueError('Délimiteurs mathématiques non fermés.')
    coverage = {c.source_id: c for c in draft.coverage}
    if set(coverage) != known or len(coverage) != len(draft.coverage):
        raise ValueError('Chaque source doit avoir exactement une décision de couverture.')
    for sid, item in coverage.items():
        if not set(item.entry_keys) <= keys:
            raise ValueError('Destination de couverture inconnue.')
        actual = {e.key for e in draft.entries if sid in e.source_ids}
        if set(item.entry_keys) != actual:
            raise ValueError(
                'Couverture incohérente pour ' + sid + ' : entry_keys=' + repr(item.entry_keys)
                + ', mais cette source est citée par les entrées ' + repr(sorted(actual))
                + '. Aligner les deux listes ; un rappel cité doit aussi avoir sa destination en coverage.')
    return draft


def guide_path(course):
    from src.courses import service
    return service._repository().paths(course['course_id']).root / 'study_guide.json'


def load_guide(course, plan=None):
    from src.courses import service
    plan = plan or service.load_course_plan(course)
    try:
        data = read_json(guide_path(course))
        if (not plan or data.get('schema_version') != VERSION or data.get('course_id') != course['course_id']
                or data.get('file_hash') != course['file_hash'] or data.get('plan_version') != plan_version(plan)):
            return None
        return data
    except StorageError:
        return None


def save_guide(course, plan, sources, entries, states, *, origin='model_generation', decisions=None, objectives=None):
    data = dict(schema_version=VERSION, course_id=course['course_id'], file_hash=course['file_hash'],
                plan_version=plan_version(plan), sources=sources, entries=entries, parts=states,
                origin=origin, decisions=decisions or [], objectives=objectives or [])
    data['revision'] = digest(data)
    write_json_atomic(guide_path(course), data)
    return data


def symbol_name(name):
    """Balise les commandes mathématiques explicites, sans convertir les noms de code."""
    if '`' in name or re.search(MATH, name):
        return name
    if re.search(r'\\(?:cap|cup|emptyset|frac|sqrt|lambda|alpha|beta|gamma|delta|mu|sigma|theta|pi|sum|prod|int|mathbb|mathrm|mathbf|mathcal|operatorname|forall|exists|in|notin|leq?|geq?|neq)\b', name):
        return r'\(' + name + r'\)'
    return name


def entry_sections(entry):
    """Conserve les repères structurés dans toutes les vues de la même fiche."""
    sections = [dict(key='core', title='L’essentiel', content=entry['body'])]
    conditions = entry.get('conditions', '').strip()
    if conditions and normal(conditions) not in normal(entry['body']):
        sections.append(dict(key='conditions', title='Conditions d’utilisation', content=conditions))
    symbols = entry.get('symbols') or []
    if symbols:
        sections.append(dict(key='symbols', title='Notations',
                             content='\n'.join('- ' + symbol_name(s['name']) + ' : ' + s['meaning'] for s in symbols)))
    return sections


def entry_card(entry, guide):
    source_map = {s['id']: s for s in guide['sources']}
    pages = sorted({p for s in entry['source_ids'] for p in source_map[s].get('pages', [source_map[s]['page']])})
    card = dict(card_id=entry['id'], concept_id=entry['id'], title=entry['title'], concept_type=entry['kind'],
                primary_part_id=entry['part_id'], related_part_ids=entry.get('related_part_ids', []),
                sections=entry_sections(entry), source_pages=pages,
                illustrations=[], covered_concept_ids=[], review_provenance=guide['origin'],
                objective=entry['objective'], aliases=entry.get('aliases', []), compact=True)
    card['resources'] = [resource_view(e, guide) for e in guide['entries'] if entry['id'] in e.get('targets', [])]
    return present_card(card)


def resource_view(entry, guide):
    sources = {s['id']: s for s in guide['sources']}
    return dict(id=entry['id'], title=entry['title'], role=entry['role'], body=entry['body'],
                html=render_text(entry['body']), pages=sorted({p for s in entry['source_ids'] for p in sources[s].get('pages', [sources[s]['page']])}),
                targets=entry.get('targets', []), part_id=entry['part_id'], core_detail=entry.get('core_detail', False))


def part_cards(guide, part_id):
    return [entry_card(e, guide) for e in guide['entries'] if e['role'] == 'core'
            and (e['part_id'] == part_id or part_id in e.get('related_part_ids', []))]


def sources_from_document(document):
    """Découpe sur des lignes complètes ; conserve l'OCR et la pagination physique."""
    result = []
    for page in document['pages']:
        text = page.get('evidence_text') or page.get('raw_text') or ''
        lines, size, number = [], 0, 0
        def append():
            if lines:
                chunk = '\n'.join(lines)
                result.append(dict(id=f"p{page['page']}-{number}", page=page['page'], text=chunk,
                                   origin='pdf_ocr' if page.get('ocr_used') else 'pdf',
                                   has_visual_content=bool(page.get('has_visual_content') or page.get('image_regions')),
                                   page_rect=page.get('page_rect'),
                                   source_units=[u for u in page.get('source_units',[]) if u.get('excerpt') and u['excerpt'] in chunk],
                                   native_lines=[line for line in page.get('native_lines',[]) if line.get('text') and line['text'] in chunk]))
        for line in text.splitlines():
            if size + len(line) > 2200 and lines:
                append(); number += 1; lines = []; size = 0
            lines.append(line); size += len(line) + 1
        append()
    return result
