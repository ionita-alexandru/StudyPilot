"""Fiches relues : complément explicite des générations, lié au PDF et au plan."""
import hashlib
import json
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Literal
from src.models.card import StudyCard

class ReviewedCollection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1] = 1
    course_id: str
    file_hash: str
    provenance: Literal['editorial_review']
    review_date: str
    coverage: Literal['selection','course_review']
    cards: list[StudyCard]
    questions: dict[str, dict[str, str]] = Field(default_factory=dict)

def load_reviewed(course, plan, root, pdf_root):
    path = Path(root) / 'reviewed_cards.json'
    if not path.is_file() or not plan:
        return None
    try:
        collection = ReviewedCollection.model_validate_json(path.read_text(encoding='utf-8'))
        pdf_name = course['source_filename']
        if Path(pdf_name).name != pdf_name:
            return None
        pdf = Path(pdf_root) / pdf_name
        if (collection.course_id != course['course_id'] or collection.file_hash != course['file_hash']
                or hashlib.sha256(pdf.read_bytes()).hexdigest() != collection.file_hash):
            return None
        parts = {str(p['id']) for p in plan['parts']}
        ids=set()
        for card in collection.cards:
            if card.card_id in ids or card.primary_part_id not in parts or not set(card.related_part_ids)<=parts:
                return None
            if any(p < 1 or p > course['page_count'] for p in card.source_pages):
                return None
            ids.add(card.card_id)
        if collection.coverage=='course_review':
            report=json.loads((Path(root)/'reviewed_coverage.json').read_text(encoding='utf-8'))
            pages=report['pages'];expected=set(range(1,course['page_count']+1))
            if (report.get('course_id')!=course['course_id'] or report.get('file_hash')!=collection.file_hash
                    or {p['page'] for p in pages}!=expected or len(pages)!=len(expected)):
                return None
            for p in pages:
                linked=set(p['card_ids'])
                if p['disposition']=='covered':
                    actual={c.card_id for c in collection.cards if p['page'] in c.source_pages}
                    if not linked or linked!=actual:return None
                elif (p['disposition']!='no_new_content' or linked or not p.get('note')
                        or any(p['page'] in c.source_pages for c in collection.cards)):return None
        return collection
    except (OSError, KeyError, TypeError, ValueError, ValidationError):
        return None

