"""Contrat commun des vues d'ensemble, indépendant de la matière enseignée."""
import re
from src.courses.card_presentation import MATH, render_text

OVERVIEW_VERSION = 2
SUMMARY_WORDS = 55


def _clean(value):
    return re.sub(r'\s+', ' ', value).strip()


def validate_overview(data):
    """Refuse une réponse inadéquate plutôt que tronquer une formule ou une idée."""
    issues = []
    summary = data.get('summary')
    if not isinstance(summary, str) or len(summary.strip()) < 40:
        issues.append('summary invalide ou trop court')
    elif len(summary.split()) > SUMMARY_WORDS:
        issues.append(f'summary : {SUMMARY_WORDS} mots maximum')
    elif re.search(MATH, summary) or re.search(r'[=∑∫]|\\[a-zA-Z]+', summary):
        issues.append('summary : expliquer le sujet en prose, sans équation ni code LaTeX')
    for field in ('key_concepts', 'prerequisites', 'learning_objectives'):
        values = data.get(field)
        if not isinstance(values, list) or any(not isinstance(x, str) or not x.strip() for x in values):
            issues.append(field + ' doit être une liste de textes non vides')
        elif field != 'prerequisites' and not values:
            issues.append(field + ' doit être non vide')
        elif field == 'learning_objectives' and any(len(x.split()) > 25 for x in values):
            issues.append('learning_objectives : une capacité précise, 25 mots maximum par élément')
    why = data.get('why_important', '')
    if not isinstance(why, str) or len(why.split()) > 30:
        issues.append('why_important : texte de 30 mots maximum ou chaîne vide')
    if issues:
        raise ValueError(' ; '.join(issues))
    result = {key: _clean(data.get(key, '')) for key in ('summary', 'why_important')}
    for key in ('key_concepts', 'prerequisites', 'learning_objectives'):
        result[key] = list(dict.fromkeys(_clean(x) for x in data[key]))
    return result


def is_current(overview):
    if overview.get('status') == 'not_applicable':
        return True
    if overview.get('status') != 'draft' or overview.get('content_version') != OVERVIEW_VERSION:
        return False
    try:
        validate_overview(overview)
    except ValueError:
        return False
    return True


def overview_view(overview):
    """HTML échappé commun aux cours existants et aux nouveaux imports.

    Un ancien paragraphe reste consultable dans un détail dépliable ; il n'est
    jamais déclaré conforme au nouveau contrat sans avoir été régénéré.
    """
    result = dict(overview)
    summary = overview.get('summary', '')
    legacy = not is_current(overview)
    result['legacy'] = legacy
    result['summary_html'] = render_text(summary)
    result['why_html'] = render_text(overview.get('why_important', ''))
    result['objectives'] = [render_text(x) for x in overview.get('learning_objectives', [])]
    result['concept_items'] = [render_text(x) for x in overview.get('key_concepts', [])]
    result['prerequisite_items'] = [render_text(x) for x in overview.get('prerequisites', [])]
    return result
